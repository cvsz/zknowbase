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

The test crosses the authenticated FastAPI service boundary through ingest, document listing, search, grounded query, and delete. It uses the production upload validation/parser, SQLite metadata store, RAG service, and pinned real Qdrant service. The external Ollama adapter response is deterministic in CI so this gate does not introduce a paid API requirement or force a model download in the CI runner.

The same path proves cross-tenant listing/retrieval denial, cross-tenant read-only deletion denial, tenant-scoped vector reconciliation on delete, and Qdrant cleanup.

## Final dependency, vulnerability, and committed-secret audit

- Pull request: #40, `ci: add final dependency and secrets release gates`
- Exact final PR head: `d4b971fba4cabf4f6ee61963dfcf14ce3dedae77`
- Merge commit: `7bfff3b410497826c152804e913c1573bef74ac4`
- Security workflow run: `32246413636`, conclusion `success`
- CI run: `32246413661`, conclusion `success`
- Workflow: `.github/workflows/security.yml`

The security gate audits pinned backend production requirements with `pip-audit`, rejects high/critical frontend production findings with `npm audit --omit=dev --audit-level=high`, scans full Git history with checksum-verified Gitleaks, and runs GitHub Dependency Review on pull requests with `fail-on-severity: high`. The merged dependency baseline updated FastAPI/Starlette and Next.js to the compatible security set required to make those release gates green.

Gitleaks output is redacted and the repository policy uses only a narrow deterministic historical test-fixture allowlist rather than a broad suppression. The successful exact-head security workflow is the release evidence for no unresolved high/critical production dependency finding and no unaccepted committed-secret finding under these configured scanners.

## Backup operations deployment-contract repair

- Pull request: #42, `fix: make documented backup operations profile runnable`
- Exact final PR head: `b3134f0674561564b1d4a6df6cf63d22ad098d86`
- Merge commit: `49de90fc68d396246f84fdf7c8353a3acbdf25e0`
- CI run: `32246819439`, conclusion `success`
- Security run: `32246819435`, conclusion `success`

The final operations audit found that the documented `docker compose --profile ops run --rm backup ...` procedure lacked a matching Compose service. PR #42 added a profile-gated one-shot backup service using the production `python -m app.backup` CLI, the same data volume/Qdrant/metadata/maintenance-lock boundary, and no browser or provider credentials. CI now validates the `ops` profile and the full combined profile.

## Still open

The following release items remain intentionally open:

- final operational/deployment/security documentation audit reconciliation after the #42 repair;
- governed zworkforce consumer integration merge and cross-repository SHA evidence;
- changelog/release notes and release version/tag.
