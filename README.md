# zknowbase

Self-hosted, API-first AI Knowledge Base for organizational documents and RAG workloads. `zknowbase` is designed as the knowledge boundary for `cvsz/zworkforce`: zworkforce calls an authenticated REST/streaming API and never connects directly to Qdrant or model-provider credentials.

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
- Admin UI: dashboard, ingestion/chunk preview, vector management, RAG playground
- Server-side Next.js API proxy so the backend API key is **not exposed to browser JavaScript**
- Python SDK for zworkforce
- Docker Compose for Qdrant + Ollama + backend + frontend

## Architecture

```text
Browser
  -> Next.js Admin (server-side secret proxy)
      -> FastAPI /api/v1
          -> SQLite document metadata
          -> Qdrant vectors
          -> Embedding adapter
          -> LLM adapter

zworkforce
  -> sdk/ZKnowbaseClient + X-API-Key
      -> FastAPI /api/v1
```

The admin browser never receives `ZKB_API_KEY`. The Next.js route handler injects it server-side.

## Start locally

```bash
cp .env.example .env
# IMPORTANT: replace ZKB_API_KEY with a long random secret

docker compose up --build
```

First boot also pulls `nomic-embed-text` and `qwen2.5:3b` into Ollama. This can be large and CPU inference may be slow; use a remote provider by changing environment variables if preferred.

- Admin: `http://localhost:3000`
- API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
- Qdrant: `http://localhost:6333`

## API

All endpoints below except health require `X-API-Key`.

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

### Query

```bash
curl -s http://localhost:8000/api/v1/query \
  -H "X-API-Key: $ZKB_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is our leave approval policy?","top_k":5,"stream":false}'
```

### Streaming query

```bash
curl -N http://localhost:8000/api/v1/query \
  -H "X-API-Key: $ZKB_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Explain the onboarding workflow","top_k":5,"stream":true}'
```

Events are `sources`, repeated `token`, then `done`.

## zworkforce integration

Copy/package `sdk/zknowbase_client.py` into the zworkforce provider/tool boundary and configure:

```bash
export ZKNOWBASE_URL=http://zknowbase:8000
export ZKNOWBASE_API_KEY='...'
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

For agent systems, prefer `search()` when the agent's own model will synthesize the final answer; use `ask()` when zknowbase should own grounded generation.

## Provider configuration

Embeddings: `ollama`, `openai`, `gemini`.

LLM: `ollama`, `openai`, `anthropic`, `gemini`.

The embedding provider is intentionally separate from the LLM provider because Anthropic does not provide a general embedding endpoint through the adapter used here.

## Security notes

- Production startup rejects the default development API key.
- URL ingestion has SSRF guardrails: public HTTP(S) only, DNS resolution rejects non-global addresses, redirects are rejected, and response size is bounded. This is defense-in-depth, not a substitute for an egress proxy/pinned-destination fetcher in high-assurance deployments.
- Files are basename-normalized and size bounded.
- Cloud provider keys stay in the backend only.
- Do not expose Qdrant or Ollama directly to untrusted networks in production; the published ports are for local development.
- Production Admin UI still needs OIDC/RBAC; API-key auth is the service-to-service baseline, not full human identity governance.

## Production roadmap

See [`exec-planning.md`](./exec-planning.md). High-priority next slices are scoped service keys/audit, Postgres metadata + HA, async ingestion workers, malware/CDR scanning, OIDC/RBAC, hybrid retrieval/reranking, per-tenant collections, OpenTelemetry, and backup/restore evidence.
