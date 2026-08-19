# zknowbase

Self-hosted, API-first AI Knowledge Base for organizational documents and RAG workloads. `zknowbase` is designed as the knowledge boundary for `cvsz/zworkforce`: zworkforce calls authenticated REST/streaming APIs and never connects directly to Qdrant or model-provider credentials.

## Local-first / no recurring API cost

The default architecture is intentionally self-hosted:

- SQLite metadata and durable ingestion queue
- Qdrant vector database
- Ollama embeddings + local LLM
- local file storage
- FastAPI backend + ingestion worker
- Next.js Admin UI with local human login and viewer/admin RBAC
- Docker Compose
- in-process document security validation before parsing

No managed database, hosted identity provider, Redis, Celery, hosted queue, paid malware scanner, or paid model API is required for the core platform. OpenAI, Anthropic, and Gemini remain optional adapters only.

For larger self-hosted installations, local Postgres is available through the optional Compose `ha` profile; SQLite remains the single-node default. For stronger local upload scanning, ClamAV is available through the optional `security` profile.

## What is included

- FastAPI backend with OpenAPI docs
- synchronous and durable asynchronous PDF/Markdown/TXT ingestion
- public URL ingestion with SSRF guardrails
- pre-parser upload validation, including PDF active-content rejection
- optional local ClamAV malware scanning with fail-closed behavior
- DB-backed ingestion jobs with leases, heartbeat renewal, retries, crash recovery, cancellation, and worker ownership
- SQLite WAL queue for the default local deployment
- optional Postgres `FOR UPDATE SKIP LOCKED` queue for multiple local workers
- LangChain text splitting
- Qdrant dense-vector retrieval
- Ollama local embeddings + LLM by default
- optional OpenAI/Gemini embeddings and OpenAI/Anthropic/Gemini LLM adapters
- grounded answers with source/chunk citations and relevance scores
- SSE query endpoint with native Ollama/OpenAI token streaming
- scoped, revocable, rotatable service API keys with durable security audit
- local scrypt Admin login, signed HttpOnly sessions, viewer/admin RBAC and same-origin checks
- Admin UI: dashboard, ingestion/chunk preview, vector management, RAG playground
- server-side Next.js API proxy so backend service credentials are not exposed to browser JavaScript
- Python SDK for zworkforce

## Architecture

```text
Browser
  -> local human login/session
      -> Next.js Admin proxy (viewer/admin RBAC)
          -> server-side scoped service key
              -> FastAPI /api/v1
                  -> upload security validation
                  -> SQLite default / local Postgres optional
                       -> document metadata
                       -> service keys + audit
                       -> durable ingestion jobs
                  -> Qdrant vectors
                  -> Ollama embeddings / LLM

Async file ingest
  -> durable DB queue
      -> local worker
          -> upload security validation / optional local ClamAV
          -> parser/chunker
          -> Ollama embedding
          -> Qdrant

zworkforce
  -> ZKnowbaseClient + scoped X-API-Key
      -> FastAPI /api/v1
```

## First-time local setup

There are **no default Admin UI credentials**. Create local auth configuration before the first Compose startup.

```bash
cp .env.example .env

# Generate a scrypt admin hash without placing the password in argv/shell history.
cd frontend
read -rsp "Admin password: " PASS
printf '%s' "$PASS" | node scripts/hash-password.mjs admin admin >> ../.env
unset PASS
cd ..

# Generate the HMAC signing secret for HttpOnly Admin sessions.
printf '\nZKB_ADMIN_SESSION_SECRET=%s\n' "$(openssl rand -hex 32)" >> .env

# Replace ZKB_API_KEY and ZKB_FRONTEND_API_KEY placeholders as documented below.
docker compose up --build
```

The generated `ZKB_ADMIN_USERS_JSON` line is single-quoted so the `$` separators in the scrypt hash remain literal when Docker Compose reads `.env`. Add a read-only human account by generating another entry with role `viewer` and combining the user objects into the same JSON array.

`ZKB_ADMIN_COOKIE_SECURE=false` is intentional for local `http://localhost`. Set it to `true` only when the Admin UI is behind HTTPS; otherwise a Secure cookie will not be sent by the browser over local HTTP.

The default command starts Qdrant, Ollama, backend, the local ingestion worker, and frontend. First boot pulls `nomic-embed-text` and `qwen2.5:3b` into Ollama. After images/models are present, the default runtime can operate locally without paid APIs.

- Admin: `http://localhost:3000`
- API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
- Qdrant: `http://localhost:6333`

### Admin roles

The browser never receives `ZKB_FRONTEND_API_KEY`. A signed human session must pass server-side authorization before the Next.js proxy injects that credential.

| Role | Admin proxy capability |
|---|---|
| `viewer` | health, document/job reads, RAG `search` and `query` |
| `admin` | viewer capabilities plus ingestion, reindex/delete and other mutations |

Viewer sessions are explicitly denied service-key and audit administration through the Admin proxy. Local user removal or a role change invalidates existing sessions on their next request. Sessions expire after eight hours.

### Optional local Postgres profile

For multiple backend/worker replicas, run Postgres locally rather than using a managed service:

```bash
# in .env
ZKB_METADATA_BACKEND=postgres
ZKB_POSTGRES_PASSWORD='replace-this'
ZKB_POSTGRES_URL='postgresql://zknowbase:replace-this@postgres:5432/zknowbase'

docker compose --profile ha up --build
```

### Optional local ClamAV profile

The default `ZKB_MALWARE_SCAN_MODE=validate` performs zero-service structural validation before parsing. It rejects unsupported/empty documents, text containing NUL bytes, malformed PDF magic/structure, and PDFs containing active-content constructs such as JavaScript, launch actions, embedded files, XFA, or rich-media/file-attachment annotations.

For local antivirus scanning as well:

```bash
# in .env
ZKB_MALWARE_SCAN_MODE=clamav

docker compose --profile security up --build
```

ClamAV runs only on the internal Compose network; port 3310 is not published to the host. When `clamav` mode is selected, scanner timeout/unavailability or an unexpected scanner response fails closed. `/api/v1/health` reports scanner readiness.

The local HA and security profiles can be combined:

```bash
docker compose --profile ha --profile security up --build
```

## API scopes

`GET /api/v1/health` is unauthenticated. Other endpoints require `X-API-Key` and the corresponding service-key scope.

| Scope | Endpoints |
|---|---|
| `knowledge:read` | documents, ingestion job status, search, query/SSE |
| `knowledge:write` | sync/async ingest, preview, reindex, delete, cancel queued jobs |
| `keys:admin` | create/list/rotate/revoke service keys |
| `audit:read` | security audit events |

## Core API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/health` | backend/Qdrant/metadata/queue/scanner readiness |
| POST | `/api/v1/ingest` | synchronous PDF/MD/TXT ingestion |
| POST | `/api/v1/ingest/url` | synchronous public URL ingestion |
| POST | `/api/v1/ingest/async` | durable file enqueue; returns HTTP 202 |
| POST | `/api/v1/ingest/url/async` | durable URL enqueue; returns HTTP 202 |
| GET | `/api/v1/ingest/jobs` | list ingestion jobs |
| GET | `/api/v1/ingest/jobs/{id}` | job status/attempt/lease/error |
| DELETE | `/api/v1/ingest/jobs/{id}` | cancel a job while it is still queued |
| POST | `/api/v1/ingest/preview` | security-check and preview chunks |
| GET | `/api/v1/documents` | document lifecycle records |
| POST | `/api/v1/documents/{id}/reindex` | synchronous reindex; blocked while async job active |
| DELETE | `/api/v1/documents/{id}` | remove metadata/file/vectors; blocked while async job active |
| POST | `/api/v1/search` | vector search without generation |
| POST | `/api/v1/query` | grounded RAG answer; `stream=true` uses SSE |
| POST | `/api/v1/service-keys` | create scoped key; secret returned once |
| GET | `/api/v1/service-keys` | list key metadata; never returns plaintext |
| POST | `/api/v1/service-keys/{id}/rotate` | atomically replace/revoke a key |
| DELETE | `/api/v1/service-keys/{id}` | revoke a key |
| GET | `/api/v1/audit` | security audit events |

### Durable async ingestion example

```bash
curl -s -X POST http://localhost:8000/api/v1/ingest/async \
  -H "X-API-Key: $ZKNOWBASE_WRITE_KEY" \
  -F 'file=@employee-handbook.pdf'
```

The response contains both a queued document record and a job ID. Poll locally:

```bash
curl -s http://localhost:8000/api/v1/ingest/jobs/JOB_ID \
  -H "X-API-Key: $ZKNOWBASE_READ_KEY"
```

Job lifecycle:

```text
queued -> processing -> completed
                  \-> queued (retry)
                  \-> failed
queued -> cancelled
```

The worker renews a lease while processing. If a worker crashes, an expired lease is requeued while attempts remain; after the retry budget is exhausted the job and document are reconciled to `failed`. Completion/failure writes are accepted only from the worker that owns the current lease.

## Service-key provisioning

Use the bootstrap key only for initial provisioning/migration:

```bash
curl -s http://localhost:8000/api/v1/service-keys \
  -H "X-API-Key: $ZKB_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"name":"zworkforce","scopes":["knowledge:read"]}'
```

The response contains the generated secret exactly once. Store it in your local secret manager/environment and configure zworkforce with that key. Only its digest, prefix, scopes, and lifecycle metadata are persisted.

For the Admin UI, provision `knowledge:read` + `knowledge:write`, put that service key in `ZKB_FRONTEND_API_KEY`, then restart the frontend. After consumers have scoped keys, disable bootstrap authentication:

```bash
ZKB_BOOTSTRAP_API_KEY_ENABLED=false
```

## Query

```bash
curl -s http://localhost:8000/api/v1/query \
  -H "X-API-Key: $ZKNOWBASE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is our leave approval policy?","top_k":5,"stream":false}'
```

Streaming:

```bash
curl -N http://localhost:8000/api/v1/query \
  -H "X-API-Key: $ZKNOWBASE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Explain the onboarding workflow","top_k":5,"stream":true}'
```

SSE events are `sources`, repeated `token`, then `done`.

## zworkforce integration

Configure zworkforce with a read-only scoped service key whenever it only needs company knowledge retrieval:

```bash
export ZKNOWBASE_URL=http://zknowbase:8000
export ZKNOWBASE_API_KEY='zkb_...'
```

```python
import os
from zknowbase_client import ZKnowbaseClient

kb = ZKnowbaseClient(
    base_url=os.environ["ZKNOWBASE_URL"],
    api_key=os.environ["ZKNOWBASE_API_KEY"],
)

contexts = kb.search("expense approval workflow", top_k=5)
result = kb.ask("How do I get an expense approved?")
print(result["answer"])
print(result["sources"])
```

Prefer `search()` when zworkforce's own local model synthesizes the answer; use `ask()` when zknowbase should own grounded generation.

## Provider configuration

Default, no-API-cost path:

- embeddings: `ollama` / `nomic-embed-text`
- generation: `ollama` / `qwen2.5:3b`

Optional adapters:

- embeddings: `openai`, `gemini`
- generation: `openai`, `anthropic`, `gemini`

Leaving cloud keys empty keeps the platform on the local path.

## Security and reliability notes

- Production startup rejects the default bootstrap service key while bootstrap authentication is enabled.
- The Admin UI has no default human password; local users are scrypt-hashed and human sessions are separated from backend service credentials.
- Signed Admin sessions are HttpOnly/SameSite=Strict, role checked server-side, and same-origin checks are required for state-changing proxy calls.
- Generated service keys are high-entropy bearer tokens; plaintext is returned once and never persisted.
- Service-key scopes are enforced server-side and denied attempts are audited.
- File uploads are structurally validated before any parser receives their bytes; ClamAV scanning can be enabled locally without a hosted security service.
- SQLite uses WAL/busy-timeout for backend + worker concurrency; Postgres is preferred before horizontally scaling many local processes.
- Queue completion/failure requires current worker ownership; stale workers cannot overwrite reclaimed jobs.
- Async uploads reject unsupported file suffixes before entering the retry queue.
- URL ingestion permits public HTTP(S), rejects non-global DNS resolutions and redirects, and bounds response size. High-assurance deployments should additionally constrain egress at the network layer.
- Do not expose Qdrant, Ollama, or clamd directly to untrusted networks.

## Validation

GitHub Actions validates:

- backend: dependency install, Ruff, pytest, upload-security tests, queue tests and real local Postgres integration tests
- frontend: Node local-auth regression tests and Next.js production build
- compose: default SQLite stack plus `ha`, `security`, and combined local profiles

See [`exec-planning.md`](./exec-planning.md) for the remaining local-first production hardening work.
