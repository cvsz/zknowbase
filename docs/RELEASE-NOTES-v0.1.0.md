# zknowbase v0.1.0 Release Notes

## Release scope

`v0.1.0` is the first production-oriented release of zknowbase: a local-first, self-hostable AI Knowledge Base consumed by zworkforce through a governed service API boundary.

The version is aligned with the repository's existing public runtime surfaces: FastAPI reports `0.1.0` and the Admin package is `0.1.0`. This release does not introduce a compatibility-breaking API version change; service endpoints remain under `/api/v1`.

## Architecture

The zero-recurring-cost default runtime is Ollama + Qdrant + SQLite. Postgres is optional for HA/multi-replica metadata, ClamAV is optional for local malware scanning, and OIDC/observability/cloud-model providers remain optional adapters. No Redis, Celery, hosted identity provider, managed vector database, or paid telemetry service is required.

## Production capabilities

The release includes authenticated ingestion, preview, document lifecycle, hybrid dense/BM25 retrieval, grounded RAG query with citations and SSE streaming, durable asynchronous ingestion, tenant isolation, scoped service keys, Admin RBAC/OIDC, encrypted backup/restore, local OpenTelemetry/Prometheus/Grafana observability, Python SDK support, and governed zworkforce knowledge tools.

## Security boundary

Tenant identity is derived from the authenticated service principal and propagated across metadata, ingestion jobs, Qdrant payloads, retrieval, lifecycle mutations, key administration, and audit records. Cross-tenant negative paths are tested. Service credentials remain server-side. zworkforce uses tenant-bound `knowledge:read` credentials and cannot bypass its ToolExecutor governance path or access Qdrant directly.

Portable backups support authenticated AES-256-GCM encryption with operator-owned local key material. Upload validation rejects active PDF content and optional ClamAV mode fails closed.

## Validation evidence

Release evidence includes real Postgres integration, real Qdrant shared-collection lifecycle and isolation tests, authenticated production-style E2E, destructive backup/restore drill, bounded local performance validation, dependency audit, committed-secret scanning, all supported Compose profile validation, and governed zworkforce integration merged to consumer `main` as `00b1aa3db1c9da15e8eb4e635b455181d1c03213`.

## Operational notes

Production operators should follow `docs/PRODUCTION-DEPLOYMENT.md`, `SECURITY.md`, `docs/ENCRYPTION-POLICY.md`, `docs/OBSERVABILITY-SLO.md`, and the backup/restore runbooks. Provision dedicated tenant-scoped service keys, disable bootstrap authentication after provisioning where practical, use TLS across host trust boundaries, protect backup encryption material independently, and calibrate initial SLOs against the deployment's real workload.

## Known limitations

- Local-first defaults prioritize a single-node deployment; multi-replica operation requires the optional Postgres path and external operational coordination for shared local artifacts.
- Initial SLO targets and performance guardrails require calibration for production corpus size, hardware, model, and concurrency.
- Cloud model adapters may incur provider costs when explicitly configured; they are not part of the zero-cost default path.
- Final release status is not established until the release candidate is green on exact-head CI/Security, merged to `main`, and the `v0.1.0` tag is verified against that exact final commit.
