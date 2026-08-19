# zknowbase — Execution Planning

## Mission
Build a production-oriented, self-hostable AI Knowledge Base consumed by `cvsz/zworkforce`.

## Architecture principles
1. API-first boundary: zworkforce never reaches the vector DB directly.
2. Fail closed: API key required for all `/api/v1/*` endpoints except health/readiness.
3. Provider isolation: embeddings and LLMs are adapters; ingestion/retrieval are provider-agnostic.
4. Durable metadata: document lifecycle lives in SQLite; vectors live in Qdrant.
5. Traceable answers: every answer returns source chunks, document IDs, and relevance scores.
6. Safe ingestion: bounded uploads, explicit content types, SSRF-resistant URL ingestion, bounded response size.
7. Local-first: Qdrant + Ollama run in Docker; OpenAI-compatible, Anthropic, and Gemini LLM adapters are configurable.
8. Idempotent lifecycle: deleting/reindexing a document also reconciles vectors.

## Delivery slices

### S1 — Backend core
- [x] FastAPI app/config/security
- [x] SQLite document metadata store
- [x] Qdrant vector store
- [x] chunking/parser layer
- [x] provider adapters
- [x] health/readiness

### S2 — API surface
- [x] `POST /api/v1/ingest`
- [x] `POST /api/v1/ingest/preview`
- [x] `POST /api/v1/query` JSON + SSE
- [x] `POST /api/v1/search`
- [x] `GET /api/v1/documents`
- [x] `POST /api/v1/documents/{doc_id}/reindex`
- [x] `DELETE /api/v1/documents/{doc_id}`

### S3 — Admin UI
- [x] dashboard
- [x] drag/drop document ingestion + preview
- [x] vector/document management
- [x] RAG playground with source/relevance visualization

### S4 — Consumer SDK
- [x] sync Python client
- [x] `ask`, `ask_stream`, `search`, `ingest_file`, document operations
- [x] zworkforce integration example

### S5 — Operations
- [x] Dockerfiles
- [x] Compose: frontend/backend/Qdrant/Ollama
- [x] `.env.example`
- [x] backend unit tests
- [x] CI lint/test/build workflow

## Production hardening backlog
- [ ] Replace single API key with scoped service keys + rotation/audit table.
- [ ] Postgres metadata backend for HA/multi-replica deployments.
- [ ] Queue-backed asynchronous ingestion for very large corpora.
- [ ] Malware scanning / CDR before parsing untrusted uploads.
- [ ] OIDC/RBAC for Admin UI.
- [ ] Hybrid BM25+dense retrieval + reranker.
- [ ] Per-tenant collections and encryption policy.
- [ ] OpenTelemetry traces/metrics and SLO dashboards.
- [ ] Backup/restore runbook for SQLite/Postgres and Qdrant snapshots.
- [ ] zworkforce native module wiring after consumer-side interface review.

## Acceptance gates
- `pytest` backend tests green.
- Python syntax/import validation green.
- Frontend `npm run build` green.
- Docker Compose config validates.
- No secrets committed.
- API auth rejects missing/invalid keys.
- Query citations contain document/chunk identity.
- Delete removes both metadata and vectors.
