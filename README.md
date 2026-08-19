# zknowbase

Self-hosted, API-first AI Knowledge Base for organizational documents and RAG workloads. `zknowbase` is designed as the knowledge boundary for `cvsz/zworkforce`: zworkforce calls authenticated REST/streaming APIs and never connects directly to Qdrant or model-provider credentials.

## Local-first / no recurring API cost

The default architecture is intentionally self-hosted:

- SQLite metadata and durable ingestion queue
- Qdrant vector database
- Ollama embeddings + local LLM
- local file storage
- FastAPI backend + ingestion worker
- Next.js Admin UI
- Docker Compose

No managed database, Redis, Celery, hosted queue, or paid model API is required for the core platform. OpenAI, Anthropic, and Gemini remain optional adapters only.

For larger self-hosted installations, local Postgres is available through the optional Compose `ha` profile; SQLite remains the single-node default.

## What is included

- FastAPI backend with OpenAPI docs
- synchronous and durable asynchronous PDF/Markdown/TXT ingestion
- public URL ingestion with SSRF guardrails
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
- Admin UI: dashboard, ingestion/chunk preview, vector management, RAG playground
- server-side Next.js API proxy so service credentials are not exposed to browser JavaScript
- Python SDK for zworkforce

## Architecture

```text
Browser
  -> Next.js Admin (server-side scoped key)
      -> FastAPI /api/v1
          -> SQLite default / local Postgres optional
               -> document metadata
               -> service keys + audit
               -> durable ingestion jobs
          -> Qdrant vectors
          -> Ollama embeddings / LLM

Async ingest
  -> durable DB queue
      -> local worker
          -> parser/chunker
          -> Ollama embedding
          -> Qdrant

zworkforce
  -> ZKnowbaseClient + scoped X-API-Key
      -> FastAPI /api/v1
```

## Start locally

```bash
cp .env.example .env
# Replace bootstrap and frontend key placeholders before production use.
docker compose up --build
```

The default command starts Qdrant, Ollama, backend, the local ingestion worker, and frontend. First boot pulls `nomic-embed-text` and `qwen2.5:3b` into Ollama. After images/models are present, the default runtime can operate locally without paid APIs.

- Admin: `http://localhost:3000`
- API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
- Qdrant: `http://localhost:6333`

### Optional local Postgres profile

For multiple backend/worker replicas, run Postgres locally rather than using a managed service:

```bash
# in .env
ZKB_METADATA_BACKEND=postgres
ZKB_POSTGRES_PASSWORD='replace-this'
ZKB_POSTGRES_URL='postgresql://zknowbase:replace-this@postgres:5432/zknowbase'

docker compose --profile ha up --build
```

## API scopes

`GET /api/v1/health` is unauthenticated. Other endpoints require `X-API-Key` and the corresponding scope.

| Scope | Endpoints |
|---|---|
| `knowledge:read` | documents, ingestion job status, search, query/SSE |
| `knowledge:write` | sync/async ingest, preview, reindex, delete, cancel queued jobs |
| `keys:admin` | create/list/rotate/revoke service keys |
| `audit:read` | security audit events |

## Core API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/health` | backend/Qdrant/metadata/queue readiness |
| POST | `/api/v1/ingest` | synchronous PDF/MD/TXT ingestion |
| POST | `/api/v1/ingest/url` | synchronous public URL ingestion |
| POST | `/api/v1/ingest/async` | durable file enqueue; returns HTTP 202 |
| POST | `/api/v1/ingest/url/async` | durable URL enqueue; returns HTTP 202 |
| GET | `/api/v1/ingest/jobs` | list ingestion jobs |
| GET | `/api/v1/ingest/jobs/{id}` | job status/attempt/lease/error |
| DELETE | `/api/v1/ingest/jobs/{id}` | cancel a job while it is still queued |
| POST | `/api/v1/ingest/preview` | preview chunks |
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

- Production startup rejects the default bootstrap key while bootstrap authentication is enabled.
- Generated service keys are high-entropy bearer tokens; plaintext is returned once and never persisted.
- Scopes are enforced server-side and denied attempts are audited.
- SQLite uses WAL/busy-timeout for backend + worker concurrency; Postgres is preferred before horizontally scaling many local processes.
- Queue completion/failure requires current worker ownership; stale workers cannot overwrite reclaimed jobs.
- Async uploads reject unsupported file suffixes before entering the retry queue.
- URL ingestion permits public HTTP(S), rejects non-global DNS resolutions and redirects, and bounds response size. High-assurance deployments should additionally constrain egress at the network layer.
- Do not expose Qdrant or Ollama directly to untrusted networks.
- Human Admin identity still requires the local/OIDC RBAC hardening slice; service keys are the service-to-service boundary.

## Validation

GitHub Actions validates:

- backend: dependency install, Ruff, pytest, and real local Postgres integration tests
- frontend: Next.js production build
- compose: default SQLite stack and optional `--profile ha` configuration

See [`exec-planning.md`](./exec-planning.md) for the remaining local-first production hardening work.
