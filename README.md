# zknowbase

Self-hosted, API-first AI Knowledge Base for organizational documents and RAG workloads. `zknowbase` is designed as the knowledge boundary for `cvsz/zworkforce`: zworkforce calls authenticated REST/streaming APIs and never connects directly to Qdrant or model-provider credentials.

## What is included

- FastAPI backend with OpenAPI docs
- PDF, Markdown, TXT, and public URL ingestion
- LangChain text splitting
- Qdrant dense-vector retrieval
- Ollama local embeddings + LLM by default
- OpenAI/Gemini embeddings and OpenAI/Anthropic/Gemini LLM adapters
- Grounded answers with source/chunk citations and relevance scores
- SSE query endpoint with native Ollama/OpenAI token streaming
- Durable SQLite document lifecycle metadata
- Scoped, revocable, rotatable service API keys with durable security audit
- Admin UI: dashboard, ingestion/chunk preview, vector management, RAG playground
- Server-side Next.js API proxy so service credentials are not exposed to browser JavaScript
- Python SDK for zworkforce
- Docker Compose for Qdrant + Ollama + backend + frontend

## Architecture

```text
Browser
  -> Next.js Admin (server-side service key)
      -> FastAPI /api/v1
          -> SQLite document + security metadata
          -> Qdrant vectors
          -> Embedding adapter
          -> LLM adapter

zworkforce
  -> ZKnowbaseClient + scoped X-API-Key
      -> FastAPI /api/v1
```

## Start locally

```bash
cp .env.example .env
# Replace BOTH bootstrap and frontend placeholders before production.
docker compose up --build
```

First boot also pulls `nomic-embed-text` and `qwen2.5:3b` into Ollama. CPU-only inference may be slow; switch providers through environment variables when appropriate.

- Admin: `http://localhost:3000`
- API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
- Qdrant: `http://localhost:6333`

## API

`GET /api/v1/health` is unauthenticated. Other endpoints require `X-API-Key` and the corresponding scope.

| Scope | Endpoints |
|---|---|
| `knowledge:read` | documents list, search, query/SSE |
| `knowledge:write` | ingest, preview, reindex, delete |
| `keys:admin` | create/list/rotate/revoke service keys |
| `audit:read` | read security audit events |

Core endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/health` | backend/Qdrant/metadata readiness |
| POST | `/api/v1/ingest` | ingest PDF/MD/TXT multipart file |
| POST | `/api/v1/ingest/url` | ingest public HTTP(S) URL |
| POST | `/api/v1/ingest/preview` | preview document chunks |
| GET | `/api/v1/documents` | list document lifecycle records |
| POST | `/api/v1/documents/{id}/reindex` | re-fetch/re-parse and replace vectors |
| DELETE | `/api/v1/documents/{id}` | remove metadata, file, and vectors |
| POST | `/api/v1/search` | vector search without LLM generation |
| POST | `/api/v1/query` | grounded RAG answer; `stream=true` uses SSE |
| POST | `/api/v1/service-keys` | create a scoped service key; secret returned once |
| GET | `/api/v1/service-keys` | list key metadata; never returns key plaintext |
| POST | `/api/v1/service-keys/{id}/rotate` | atomically replace/revoke a key |
| DELETE | `/api/v1/service-keys/{id}` | revoke a key |
| GET | `/api/v1/audit` | list authentication/authorization audit events |

### Provision a read-only zworkforce key

Use the bootstrap key only for initial provisioning/migration:

```bash
curl -s http://localhost:8000/api/v1/service-keys \
  -H "X-API-Key: $ZKB_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"name":"zworkforce","scopes":["knowledge:read"]}'
```

The response contains `secret` exactly once. Store it in your secret manager and configure zworkforce with that service key. The database stores only its digest, prefix, scopes, lifecycle timestamps, and audit metadata.

For an Admin UI key, provision both `knowledge:read` and `knowledge:write`, place that value in `ZKB_FRONTEND_API_KEY`, then restart the frontend. Once every consumer uses scoped keys, set:

```bash
ZKB_BOOTSTRAP_API_KEY_ENABLED=false
```

and restart the backend to disable the bootstrap/root key.

### Query

```bash
curl -s http://localhost:8000/api/v1/query \
  -H "X-API-Key: $ZKNOWBASE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is our leave approval policy?","top_k":5,"stream":false}'
```

### Streaming query

```bash
curl -N http://localhost:8000/api/v1/query \
  -H "X-API-Key: $ZKNOWBASE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Explain the onboarding workflow","top_k":5,"stream":true}'
```

SSE events are `sources`, repeated `token`, then `done`.

## zworkforce integration

Configure the consumer with a scoped service key rather than the bootstrap/root key:

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

Prefer `search()` when zworkforce's own model will synthesize the answer; use `ask()` when zknowbase should own grounded generation.

## Provider configuration

Embeddings: `ollama`, `openai`, `gemini`.

LLM: `ollama`, `openai`, `anthropic`, `gemini`.

Embedding and generation providers are intentionally separate adapters.

## Security notes

- Production startup rejects the default bootstrap key while bootstrap authentication is enabled.
- Generated service keys are high-entropy bearer tokens; plaintext is returned once and never persisted.
- Scopes are enforced server-side and denied attempts are audited.
- Rotation creates the replacement and revokes the old key in one SQLite transaction.
- Expired/revoked/unknown service keys fail closed.
- URL ingestion has SSRF guardrails: public HTTP(S) only, DNS resolution rejects non-global addresses, redirects are rejected, and response size is bounded. For high-assurance deployments, add a pinned-egress proxy.
- Files are basename-normalized and size bounded.
- Cloud provider credentials remain backend-only.
- Do not expose Qdrant or Ollama directly to untrusted networks in production.
- Human Admin identity still requires the OIDC/RBAC production-hardening slice; service keys are not a substitute for human identity governance.

## Validation

GitHub Actions validates independent pull-request gates:

- backend: dependency install, Ruff, pytest
- frontend: dependency install and Next.js production build
- compose: `docker compose config --quiet`

## Production roadmap

See [`exec-planning.md`](./exec-planning.md). Remaining hardening includes Postgres + HA, async ingestion workers, malware/CDR scanning, OIDC/RBAC, hybrid retrieval/reranking, multi-tenancy/encryption policy, OpenTelemetry/SLOs, backup/restore evidence, and native zworkforce tool wiring.
