# Changelog

All notable production changes to zknowbase are documented here.

## 0.1.0 — 2026-08-19

Initial production release candidate for the self-hosted zknowbase knowledge platform.

### Added

- FastAPI service API for file/URL ingestion, preview, document lifecycle, dense/hybrid search, grounded query, JSON responses, and SSE streaming.
- Local-first Ollama inference and embeddings with optional OpenAI, Anthropic, and Gemini adapters.
- Shared Qdrant vector storage with authenticated tenant payload enforcement on upsert, search, delete, reindex, and citation validation.
- SQLite metadata default plus optional self-hosted Postgres HA/multi-replica backend.
- Durable database-backed asynchronous ingestion with bounded retries, leases, worker ownership, cancellation, and tenant-bound queue state; no Redis/Celery dependency.
- Scoped service keys with hash-only persistence, rotation, revocation, expiry, audit records, and durable tenant ownership.
- Local Admin dashboard with human authentication/RBAC, optional self-hosted OIDC, document management, ingestion preview, vector/reindex controls, and RAG playground.
- Local upload security including active-PDF rejection and optional fail-closed ClamAV profile.
- Native authenticated AES-256-GCM portable backup encryption, tenant-aware SQLite/Postgres/Qdrant backup/restore, safety backups, and destructive DR drill evidence.
- OpenTelemetry-compatible tracing, Prometheus metrics, optional local Collector/Prometheus/Grafana profile, dashboards, and initial SLO objectives.
- Python SDK and governed zworkforce integration through read-only `knowledge_search` / `knowledge_ask` tools using tenant-bound `knowledge:read` credentials.
- Production E2E, real Postgres/Qdrant CI coverage, dependency/secret security gates, load/performance guardrails, and deployment/upgrade/rollback documentation.

### Security

- Authentication, authorization, tenant context, upload validation, retrieval isolation, and governed consumer context fail closed.
- Browser clients never receive zknowbase service credentials.
- Cross-tenant document, vector, queue, service-key, audit, delete, reindex, and retrieval access is denied and regression-tested.
- Optional cloud providers remain server-side adapters and are not required by the default runtime.

### Compatibility

- Default deployment remains local-first with Ollama + Qdrant + SQLite and no recurring API cost after required artifacts are present.
- Postgres, ClamAV, OIDC, observability, cloud-model providers, and HA features are optional self-hosted/adapter paths.
- `zworkforce` consumes knowledge only through the zknowbase service API/SDK boundary; agents do not access Qdrant directly.
