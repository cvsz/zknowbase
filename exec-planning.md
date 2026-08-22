# zknowbase — Execution Planning

## Mission
Build a production-oriented, self-hostable AI Knowledge Base consumed by `cvsz/zworkforce` with a **local-first / zero recurring API cost** default architecture.

## Hard constraints
1. Default runtime must work fully offline after model images/artifacts are present.
2. Default stack must not require paid SaaS, managed databases, paid queues, or paid model APIs.
3. Ollama, Qdrant, SQLite, local files, Docker/Compose are the baseline path.
4. Cloud model providers remain optional adapters only and are never required for core functionality.
5. Optional Postgres must run locally/self-hosted; SQLite remains the default for a single-node deployment.
6. Background ingestion must not require Redis, Celery, or an external broker.
7. Upload security must be available locally without a paid malware-scanning API.
8. Admin human authentication must work locally without a hosted identity provider.

## Architecture principles
1. API-first boundary: zworkforce never reaches the vector DB directly.
2. Fail closed: API key required for all `/api/v1/*` endpoints except health/readiness.
3. Provider isolation: embeddings and LLMs are adapters; ingestion/retrieval are provider-agnostic.
4. Durable metadata: SQLite by default; optional local Postgres for multi-replica/HA; vectors live in Qdrant.
5. Traceable answers: every answer returns source chunks, document IDs, and relevance scores.
6. Safe ingestion: bounded uploads, explicit content types, SSRF-resistant URL ingestion, bounded response size.
7. Local-first inference: Qdrant + Ollama run in Docker; OpenAI, Anthropic, and Gemini are opt-in only.
8. Idempotent lifecycle: deleting/reindexing a document also reconciles vectors.
9. Least privilege: generated service keys are scoped, revocable/rotatable, and never persisted in plaintext.
10. Durable local work: ingestion jobs use the metadata DB for leases/retries instead of a paid/external queue.
11. Parse only after upload security validation; local ClamAV mode fails closed when selected.
12. Human Admin sessions and backend service credentials are separate trust boundaries.
13. Tenant identity is derived from the authenticated principal and enforced server-side; client filters never define authorization.
14. The shared Qdrant collection is tenant-partitioned by mandatory payload filters on every supported vector operation rather than by dynamically created per-tenant collections.

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

### S6 — Scoped service authentication
- [x] generated service keys stored as hashes only
- [x] scopes: `knowledge:read`, `knowledge:write`, `keys:admin`, `audit:read`
- [x] expiry, revocation, last-used tracking, and atomic rotation
- [x] service-key lifecycle API
- [x] durable authentication/authorization audit table
- [x] bootstrap/root key can be disabled after provisioning
- [x] separate server-side Admin UI credential

### S7 — Local metadata scale-out
- [x] SQLite remains zero-cost single-node default
- [x] optional local Postgres metadata backend
- [x] pooled Postgres connections for multi-replica application instances
- [x] document lifecycle parity across SQLite/Postgres
- [x] scoped-key/audit parity across SQLite/Postgres
- [x] transaction-safe service-key rotation in Postgres
- [x] optional Docker Compose `ha` profile for local Postgres
- [x] CI integration test against real Postgres service

### S8 — Durable local asynchronous ingestion
- [x] DB-backed queue; no Redis/Celery/external broker required
- [x] SQLite queue with WAL/busy-timeout for backend+worker concurrency
- [x] Postgres queue with `FOR UPDATE SKIP LOCKED` multi-worker claims
- [x] worker ownership, leases, heartbeat renewal, retry budget, cancellation
- [x] local worker container sharing uploaded-file volume
- [x] async file and URL enqueue APIs
- [x] job list/status/cancel APIs
- [x] worker and queue unit/integration coverage

### S9 — Local upload security / content disarm boundary
- [x] extension + empty-file + text-NUL validation before parsing
- [x] PDF magic/structure validation
- [x] reject PDF JavaScript, launch actions, embedded files, XFA, rich-media/active annotations
- [x] optional local ClamAV `INSTREAM` client
- [x] ClamAV mode fails closed on timeout/unavailability/unexpected scanner response
- [x] optional Compose `security` profile using pinned ClamAV LTS patch release
- [x] ClamAV TCP port remains internal to the Compose network
- [x] scanner readiness included in health response
- [x] sync ingest, preview, reindex, and async worker scan before parser execution
- [x] scanner/PDF active-content regression tests

### S10 — Local Admin human authentication and RBAC
- [x] no default human credentials
- [x] local scrypt password hashes generated without passing password in argv
- [x] signed 8-hour HttpOnly/SameSite=Strict sessions
- [x] local HTTP supported; Secure cookie is explicit for HTTPS deployments
- [x] session invalidates when the configured user is removed or its role changes
- [x] bounded in-process login attempt limiter for the default single frontend process
- [x] same-origin enforcement for login/logout and state-changing Admin proxy calls
- [x] `viewer` retrieval-only and `admin` mutation authorization at the server proxy
- [x] service key remains server-side and is injected only after human session authorization
- [x] Node auth regression tests run in CI without extra runtime dependencies

### S11 — Local hybrid retrieval
- [x] dependency-free BM25 scoring over bounded dense candidates
- [x] Qdrant remains authoritative for filters and collection boundaries
- [x] configurable dense/hybrid retrieval mode
- [x] configurable candidate multiplier and dense/lexical fusion weight
- [x] unit coverage for lexical promotion, top-k, and empty candidate behavior

### S12 — Backup/restore operational recovery
- [x] SQLite/Postgres metadata backup paths
- [x] uploaded-file archive with integrity manifest
- [x] Qdrant snapshot capture/restore with major/minor compatibility guard
- [x] owner-only backup archive permissions
- [x] pre-restore safety backup by default
- [x] operator runbook with verification, isolated restore drill, RPO/RTO evidence checklist
- [x] tenant key/job/audit ownership preserved by current Postgres backups, with deterministic legacy-v1 fallback

### S13 — Optional self-hosted OIDC login
- [x] local username/password auth remains the default and requires no IdP
- [x] authorization-code flow with PKCE and bounded state cookie
- [x] discovery issuer equality and same-origin endpoint validation
- [x] HTTPS-only IdP endpoints except loopback development
- [x] token exchange and UserInfo subject validation
- [x] configurable claim-to-viewer/admin mapping
- [x] OIDC sessions reuse the existing signed HttpOnly Admin session boundary
- [x] OIDC configuration/role/state regression tests run with the existing frontend auth gate

### S14 — Tenant isolation and encryption policy
- [x] durable tenant identity on service keys and authenticated principals
- [x] tenant ownership on SQLite/Postgres document metadata
- [x] tenant-bound synchronous ingest/query/search/list/delete/reindex lifecycle
- [x] shared Qdrant collection with mandatory tenant payload on upsert/search/delete and citation validation
- [x] tenant ownership on durable async ingestion jobs, queue reads/cancel, worker reconciliation, and Postgres/SQLite queue mappings
- [x] tenant-scoped service-key administration
- [x] tenant-scoped security-audit reads with immutable audit→tenant ownership for new events and deterministic legacy fallback
- [x] cross-tenant negative regression coverage across metadata, vector, async queue, and audit boundaries
- [x] backup/restore preserves key/job/audit tenant sidecars on current Postgres archives
- [x] explicit self-hosted encryption policy defines secrets, data-at-rest, transport, backups, key ownership/rotation, and non-claims without inventing custom cryptography

### S15 — Local observability and SLOs
- [x] OpenTelemetry-compatible tracing for API, retrieval, provider, Qdrant, ingestion, upload scanning, and database paths
- [x] bounded Prometheus request/provider/queue/auth/error metrics without secrets or raw document contents
- [x] telemetry exporter failure remains fail-open for core retrieval availability
- [x] optional local OpenTelemetry Collector + Prometheus + Grafana Compose profile; no hosted telemetry required
- [x] local API/retrieval/provider/ingestion/error/backlog dashboard provisioning
- [x] documented initial availability, latency, ingestion, queue-health, and Qdrant SLO objectives
- [x] Grafana anonymous access disabled and observability profile requires an operator-controlled local admin secret

### S16 — Governed zworkforce integration
- [x] zknowbase validates versioned governed retrieval context on the authenticated `knowledge:read` API boundary
- [x] authenticated service-key tenant remains authoritative; consumer tenant metadata cannot override it
- [x] malformed, incomplete, cross-tenant, or request-ID-inconsistent governed context fails closed
- [x] `cvsz/zworkforce` read-only `knowledge_search` / `knowledge_ask` tools merged to consumer `main`
- [x] consumer integration proven green under zworkforce branch protection and required reviewer policy
- [x] cross-repository release evidence records both final SHAs and least-privilege credential configuration

Evidence: zworkforce PR #168 (`feat: route zknowbase through governed knowledge tools`) merged to consumer `main` as `00b1aa3db1c9da15e8eb4e635b455181d1c03213`. The integration uses server-side tenant-bound `knowledge:read` credentials, ToolExecutor grants, governed tenant/actor/agent/tool/policy/request/trace context, cross-tenant response rejection, and no direct agent Qdrant path. The corresponding zknowbase release-evidence baseline is `b35f32513932aa76fe59265911f829d3cea2e5d4` before this documentation-only reconciliation.

### S17 — Production release evidence
- [x] real Postgres integration is exercised in CI
- [x] real Qdrant shared-collection lifecycle is exercised in CI with cross-tenant search/delete negative coverage
- [x] representative production E2E retrieval/ingestion validation documented
- [x] backup/restore DR drill evidence recorded, not only the runbook procedure
- [x] bounded load/performance evidence recorded against a representative local workload
- [x] final dependency/security/secrets audit evidence recorded
- [x] final operational/deployment/security documentation audit complete
- [x] changelog/release notes and release version/tag complete

Release evidence: release-candidate commit `e9ea3d69fca21bf21b3323cd289f1b5edab3787a` passed exact-head CI run `32256200249` and Security run `32256200225`, then merged through PR #49. Release `v0.1.0` resolves successfully in GitHub repository content and identifies release commit `b27352d64b200b79739653921c82551d4e06b7d6`. No open pull requests or open issues remained at final reconciliation.

## Production hardening backlog
- [x] Replace single API key with scoped service keys + rotation/audit table.
- [x] Optional local Postgres metadata backend for HA/multi-replica deployments.
- [x] Queue-backed asynchronous ingestion for large corpora without an external broker.
- [x] Malware scanning / active-content rejection before parsing untrusted uploads using self-hosted tools.
- [x] Local Admin UI human authentication + viewer/admin RBAC without mandatory SaaS identity.
- [x] Optional OIDC login adapter for self-hosted identity providers.
- [x] Hybrid BM25+dense retrieval + local reranker.
- [x] Tenant-isolated shared Qdrant storage and explicit encryption policy (chosen over per-tenant collections after enforcing authenticated-principal tenant payload boundaries).
- [x] OpenTelemetry traces/metrics and local SLO dashboards.
- [x] Backup/restore runbook for SQLite/Postgres and Qdrant snapshots.
- [x] zworkforce native module wiring after consumer-side interface review.
- [x] documentation-audit and final release evidence.

## Acceptance gates
- `pytest` backend tests green.
- Python syntax/import validation green.
- Frontend local-auth/OIDC tests and `npm run build` green.
- Docker Compose default, `ha`, `security`, `observability`, `ops`, and combined local profiles validate.
- Postgres integration tests run against an actual local Postgres service in CI.
- Qdrant lifecycle tests run against an actual pinned local Qdrant service in CI.
- Durable queue tests prove FIFO claim, worker ownership, retries, cancel, and completion.
- PDF active content and embedded files are rejected before text extraction.
- ClamAV mode fails closed and uses only the internal Compose network.
- Admin proxy requires a valid human session before injecting its service credential.
- Viewer sessions cannot perform mutation or key/audit administration through the proxy.
- No default local-admin password or committed session secret.
- No secrets committed.
- Missing/invalid/revoked/expired service keys fail closed.
- Read-only service keys cannot mutate documents.
- Service-key plaintext is never persisted and rotation revokes the old key atomically.
- Tenant principals cannot list/read/delete/reindex/search/vector-access another tenant's resources or audit stream.
- Async ingestion jobs cannot be listed/cancelled/reconciled across tenants.
- Query citations contain document/chunk/tenant identity and cannot cross the authenticated tenant boundary.
- Delete removes both metadata and vectors within the authenticated tenant boundary.
- Current Postgres backups preserve service-key, ingestion-job, and immutable audit tenant ownership.
- Encryption documentation makes no application-layer confidentiality claim beyond implemented primitives and requires encrypted storage/transport where the threat model demands it.
- Local observability does not require paid SaaS, does not expose document contents/secrets, and Grafana anonymous access remains disabled.
- Governed zworkforce retrieval uses only the service API boundary and least-privilege `knowledge:read` credentials; agents never access Qdrant directly.
- Default runtime requires no paid API, managed service, hosted identity, or external queue.

## Post-v0.1.0 execution program

`v0.1.0` is the completed production baseline. The slices below define the next evidence-driven development program toward `v0.2.0`. They are intentionally unchecked until code, tests, CI, operational evidence, and documentation prove completion. Every slice must preserve S1-S17 guarantees and the local-first / zero recurring API cost default.

### S18 — Repository governance and release safety
- [x] enable repository rules/branch protection for `main` with pull-request-only changes
- [x] require current CI and Security workflow checks before merge
- [x] prevent force-push and branch deletion for `main`
- [x] define emergency/break-glass procedure without silently bypassing evidence requirements
- [x] add CODEOWNERS/reviewer ownership for backend security, frontend auth, operations, and release-sensitive paths where appropriate
- [x] document release/tag provenance and post-release hotfix procedure
- [x] record GitHub-observable evidence that a deliberately failing PR cannot merge through the normal path
- [ ] record GitHub-observable evidence that a green PR can merge through the normal path

Acceptance: a deliberately failing PR cannot merge through the normal path, a green PR can merge, and the governance configuration is recorded as release evidence.

Evidence status: failing-path proven by PR #66 at head `131a45b375da41bc978d826d8da361b415786afe`: required `backend` failed in CI run `32427160455`, GitHub rejected an exact-head normal merge attempt with HTTP 405 citing both the failing required check and missing approving review, and PR #66 was closed unmerged. Green-path evidence remains pending successful protected merge of PR #62 with current exact-head checks and non-stale approval. See `docs/S18-REPOSITORY-GOVERNANCE-EVIDENCE.md` and `docs/RELEASE-SAFETY.md`.

### S19 — Native portable-backup confidentiality
- [x] add optional native authenticated encryption for portable backup archives using an established reviewed cryptographic library
- [x] keep the default runtime self-hosted with no hosted KMS dependency
- [x] load backup keys from operator-controlled secret files or equivalent server-side secret boundary; never from browser/public environment variables
- [x] use a versioned envelope and fresh nonce/IV per archive
- [x] bound encryption/decryption memory usage for large backups
- [x] authenticate/decrypt completely before archive parsing or destructive restore mutation
- [x] fail closed on wrong key, corruption, truncation, insecure key-file permissions, and plaintext archives when encryption is required
- [x] preserve tenant key/job/audit ownership and legacy backup compatibility according to explicit migration policy
- [x] add encrypted backup/verify/restore and negative security regression tests
- [x] update encryption and DR documentation with rotation/escrow/retention procedures

Evidence: PR #54 (`security: complete S19 backup confidentiality evidence`) merged as `53ae26c6086525f0e03131a1cbbce62024876bc0` after exact-head CI run `32361797503` (CI #156) and Security run `32361797482` (Security #36) succeeded. PR #58 (`docs: record S19 portable backup confidentiality evidence`) merged as `82b0c1a0f7c4b09b7e1c9edbf9b815ab3737eb8a` after exact-head CI #178 and Security #58 succeeded. `docs/S19-PORTABLE-BACKUP-CONFIDENTIALITY-EVIDENCE.md` records the implementation, negative-security, tenant-compatibility, and key-rotation/escrow/retention evidence.

Acceptance: an encrypted archive exposes no plaintext knowledge content at rest, tamper/wrong-key restore fails before application mutation, and both SQLite and Postgres recovery remain proven.

### S20 — Retrieval quality evaluation and regression gates
- [ ] define a local evaluation dataset format with question, expected source/document constraints, and optional answer rubric
- [ ] add offline retrieval metrics such as Recall@K, MRR/nDCG where appropriate, citation hit rate, and grounded-answer checks
- [ ] compare dense-only versus hybrid retrieval under the same tenant-authoritative boundary
- [ ] add deterministic local benchmark fixtures that require no paid model API
- [ ] add configurable quality thresholds to CI without introducing flaky LLM-judge dependence
- [ ] record retrieval latency/quality trade-offs and recommended default tuning

Acceptance: retrieval changes cannot silently regress the committed local evaluation baseline beyond documented thresholds.

### S21 — Ingestion lifecycle and connector expansion
- [ ] add content-hash based duplicate detection/idempotent ingestion where it does not violate explicit reindex semantics
- [ ] add safe scheduled/recurrent reindex primitives using the existing durable DB queue rather than an external scheduler/queue dependency
- [ ] define connector adapter boundary for additional self-hostable sources without embedding third-party credentials in browser clients
- [ ] preserve SSRF, upload-security, tenant, audit, retry, and cancellation guarantees for every connector
- [ ] expose ingestion provenance and last-success/last-failure metadata for operators
- [ ] add connector contract tests and failure/retry coverage

Acceptance: connector additions remain tenant-bound, auditable, resumable, bounded, and local-first.

### S22 — Admin operations and knowledge-quality UX
- [ ] expose tenant-safe ingestion/job health, failures, retry state, and provenance in Admin UI
- [ ] add document/chunk inspection with source metadata while respecting viewer/admin authorization
- [ ] add retrieval-debug view for dense score, lexical contribution, final rank, and active server-authoritative filters without exposing secrets
- [ ] add safe bulk reindex/delete workflows with explicit confirmation and bounded operations
- [ ] add accessibility and keyboard-navigation regression coverage for critical Admin flows
- [ ] preserve server-side service credentials and same-origin mutation enforcement

Acceptance: operators can diagnose ingestion and retrieval quality without shell/database access and without weakening the browser trust boundary.

### S23 — Scale, resilience, and failure-recovery hardening
- [ ] define supported single-node and Postgres multi-replica deployment envelopes
- [ ] add multi-worker concurrency/load tests for queue leases, renewal, retries, and cancellation
- [ ] add controlled Qdrant/Postgres/Ollama outage and recovery tests for documented failure modes
- [ ] verify bounded retries/backoff and no unbounded memory/disk growth during dependency outages
- [ ] add graceful shutdown/drain evidence for backend and worker processes
- [ ] calibrate SLOs using collected benchmark evidence and document capacity assumptions

Acceptance: representative dependency failures recover without cross-tenant leakage, duplicate destructive mutation, stuck leases, or uncontrolled resource growth.

### S24 — Governed zworkforce knowledge capabilities v2
- [ ] refresh `cvsz/zworkforce` consumer contract before changes
- [ ] add optional structured retrieval metadata needed for governed agent decisions without exposing internal vector-store access
- [ ] propagate stable trace/request IDs across zworkforce → zknowbase → provider/vector spans
- [ ] add explicit policy hooks for allowed knowledge domains/document classes where zworkforce governance requires them
- [ ] keep authenticated zknowbase service-key tenant authoritative over all consumer metadata
- [ ] expand cross-repository integration tests for denied policy, tenant mismatch, timeouts, cancellation, and degraded knowledge service behavior

Acceptance: agents gain richer governed knowledge capabilities while remaining least-privilege and unable to reach Qdrant directly.

### S25 — v0.2.0 production release evidence
- [ ] all S18-S24 release-scoped items implemented or explicitly deferred with documented rationale
- [ ] exact-head CI and Security workflows green
- [ ] no open failing/stale release PRs or unresolved high/critical production vulnerabilities
- [ ] real Postgres/Qdrant integration and bounded performance evidence green
- [ ] encrypted-backup DR drill completed if S19 is release-scoped
- [ ] retrieval-quality regression evidence recorded
- [ ] operational/security/deployment/upgrade/rollback documentation reconciled
- [ ] zworkforce compatibility evidence recorded for the final consumer SHA
- [ ] changelog and `v0.2.0` release notes complete
- [ ] release tag resolves exactly to the approved release commit

Final verdict for this program must be exactly one of:

`V0.2.0 FINAL RELEASE — APPROVED`

or

`V0.2.0 FINAL RELEASE — BLOCKED`

Do not mark S18-S25 complete based on intent, partial implementation, local-only assumptions, or documentation without executable evidence.

## Post-v0.1 execution priority
1. Fix any regression or failing CI/security gate on `main` first.
2. S18 repository governance and release safety.
3. S19 native portable-backup confidentiality.
4. S20 retrieval quality evaluation/regression gates.
5. S23 scale/resilience hardening when it blocks correctness or SLO evidence.
6. S21 ingestion lifecycle/connectors.
7. S22 Admin operations/quality UX.
8. S24 governed zworkforce capabilities v2.
9. S25 final `v0.2.0` release evidence.

One focused PR per vertical slice. Never weaken S1-S17 security, tenant, local-first, CI, DR, or governance guarantees merely to make a new feature pass.
