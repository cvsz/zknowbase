# S17 Production Evidence

This document records evidence that is already merged and validated. It does not claim completion for release gates that remain open.

## Disaster-recovery drill

- Pull request: #36, `test: add executable local disaster recovery drill`
- Exact PR head: `b2684c08141d9f209cdbf19eabe8cd275f15a4fe`
- Merge commit: `7e0a04e75274f0e148a268dd280927578ad7b8c7`
- CI run: `32243837001`, conclusion `success`
- Executable evidence: `backend/tests/test_dr_drill_integration.py`

The drill uses the pinned real Qdrant CI service and the native backup/restore path. It creates tenant-bound SQLite metadata, an uploaded source file, and a Qdrant vector; creates a backup; deliberately deletes the metadata, corrupts the upload, and deletes the Qdrant collection; then restores and verifies the original metadata, tenant identity, upload bytes, and searchable vector payload. The archive owner-only permission requirement is also asserted.

This is executable destructive recovery evidence rather than a runbook-only claim.

## Bounded local performance evidence

- Pull request: #37, `perf: publish bounded real-Qdrant load evidence`
- Exact PR head: `b653ae3a5c94bae6924c8a250cb6262884dbe779`
- Merge commit: `063d2d5cff009e5ed9e937a6720dd611bf93cf7c`
- CI run: `32244108402`, conclusion `success`
- Performance job: `96040808867`, conclusion `success`
- Benchmark: `backend/scripts/benchmark_qdrant.py`
- Operational documentation: `docs/PERFORMANCE.md`

The CI workload is bounded to 512 tenant-scoped vector points, 200 tenant-filtered searches, concurrency 8, 32-dimensional deterministic vectors, top-10 retrieval, zero accepted search errors, and a 2-second p95 regression guardrail. The performance job runs against pinned Qdrant `v1.15.1` and publishes `performance-report.json` as a workflow artifact.

The same run also completed backend lint/tests, frontend auth tests and production build, and Compose validation for default, HA, security, observability, and combined profiles.

This benchmark is a repeatable component regression guardrail. It is not represented as a universal end-to-end `/query` latency guarantee because Ollama model latency and deployment hardware remain workload-specific.

## Representative production service-API E2E

- Pull request: #39, `test: add representative production API E2E evidence`
- Exact final PR head: `ec993e88f30604372d7f2a06e01a6458ac42eba8`
- Merge commit: `2bbae7638d41ce17d559e148d5763cc6df568f5e`
- CI run: `32245742977`, conclusion `success`
- Executable evidence: `backend/tests/test_production_e2e_integration.py`

The test crosses the authenticated FastAPI service boundary through `POST /api/v1/ingest`, `GET /api/v1/documents`, `POST /api/v1/search`, `POST /api/v1/query`, and `DELETE /api/v1/documents/{doc_id}`. It uses the production upload validation/parser, SQLite metadata store, RAG service, and pinned real Qdrant `v1.15.1`; only the external Ollama inference adapter response is deterministic in CI so the release gate does not require a paid API or model download.

The same executable path proves tenant B cannot list or retrieve tenant A data, a tenant-B read-only key cannot delete the tenant-A document, tenant-A deletion reconciles Qdrant vectors, and the temporary Qdrant collection is deleted during cleanup. Exact-head CI completed backend Ruff and 88 tests, frontend local-auth/OIDC tests and Next.js production build, all default/HA/security/observability/combined Compose validations, and the bounded performance job.

## Still open

The following release items remain intentionally open:

- final dependency/security/secrets audit evidence;
- final operational/deployment/security documentation audit;
- changelog/release notes and release version/tag;
- governed zworkforce consumer integration merge and cross-repository SHA evidence.
