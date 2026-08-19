# Production deployment and operations

This guide defines the supported self-hosted production deployment boundary for zknowbase. It complements `SECURITY.md`, `docs/ENCRYPTION-POLICY.md`, `docs/OBSERVABILITY-SLO.md`, and `docs/BACKUP-RESTORE-RUNBOOK.md`.

## Supported architecture

The default production topology remains local-first and requires no paid SaaS:

- FastAPI backend and DB-backed ingestion worker
- SQLite for single-node metadata/queue durability
- optional self-hosted Postgres for multi-replica deployments
- shared Qdrant collection with mandatory server-side tenant payload enforcement
- Ollama for default embeddings and generation
- Next.js Admin UI with local auth/RBAC or optional self-hosted OIDC
- local filesystem uploads/backups
- optional ClamAV, OpenTelemetry Collector, Prometheus, and Grafana profiles

`zworkforce` and every other consumer must use the zknowbase service API/SDK boundary. Agents and browser clients must never connect directly to Qdrant or receive zknowbase service credentials.

## Production prerequisites

Before exposing the service outside a trusted development host:

1. Replace `ZKB_API_KEY` and provision scoped service keys. Disable bootstrap authentication after provisioning where practical.
2. Configure a high-entropy `ZKB_ADMIN_SESSION_SECRET` and explicit Admin users or a reviewed self-hosted OIDC provider.
3. Use TLS at the ingress/reverse-proxy boundary whenever traffic crosses a trusted host boundary.
4. Put SQLite/Postgres data, uploads, Qdrant storage, Ollama artifacts, backups, and secret files on operator-managed encrypted storage when the data classification requires confidentiality at rest.
5. Restrict Qdrant, Ollama, Postgres, ClamAV, the OTel Collector, Prometheus, and backend-only service ports to trusted/internal networks.
6. Configure host firewall/egress policy in addition to application SSRF validation for high-assurance environments.
7. Set resource limits according to measured workload. Do not infer universal capacity from the bounded CI performance benchmark.

## Compose profiles

The repository validates these supported profiles:

- default: SQLite + backend + worker + Qdrant + Ollama + frontend
- `ha`: adds self-hosted Postgres for metadata/queue scale-out
- `security`: adds local ClamAV and fail-closed scanning when selected
- `observability`: adds local OpenTelemetry Collector, Prometheus, and authenticated Grafana
- `ops`: exposes the one-shot production backup CLI with the same data/Qdrant/metadata boundary as the running service

Profiles may be combined when their required environment values are provided. CI validates default, individual production profiles, and the combined configuration.

## Tenant and credential model

Tenant identity is derived from the authenticated service principal. Client filters and governed-context headers cannot select another tenant.

Use separate service credentials by purpose:

- `knowledge:read`: retrieval-only consumers such as governed zworkforce knowledge tools
- `knowledge:write`: ingestion/document mutation workflows
- `keys:admin`: service-key lifecycle administration
- `audit:read`: tenant-scoped security audit access

Do not place service keys in browser bundles, `NEXT_PUBLIC_*`, prompts, task payloads, source control, telemetry, or log fields. zknowbase persists only digests for generated service keys; plaintext is returned once at creation/rotation.

## zworkforce boundary

The supported consumer path is:

`zworkforce governed agent/tool runtime -> server-side zknowbase client -> /api/v1/search or /api/v1/query -> tenant-filtered Qdrant`

Production retrieval credentials should be dedicated `knowledge:read` keys bound to the expected tenant. Governed requests carry actor/agent/tool/policy/request/trace metadata, while the authenticated zknowbase principal remains the authoritative tenant identity. Missing, malformed, inconsistent, or cross-tenant governed context fails closed.

No zworkforce agent is permitted to access Qdrant directly.

## Backup and restore

Use the `ops` profile for documented backup operations. The backup implementation preserves SQLite/Postgres metadata, uploads, Qdrant snapshots, and tenant ownership sidecars.

Native portable backups support an authenticated AES-256-GCM envelope when `ZKB_BACKUP_ENCRYPTION_KEY_FILE` is configured. `ZKB_BACKUP_REQUIRE_ENCRYPTION=true` rejects plaintext verify/restore and fails startup configuration when no key file is configured. The key file must contain strict base64 for exactly 32 bytes and must be owner-only on POSIX systems.

Backup encryption does not replace encrypted live volumes, tenant authorization, key escrow, retention policy, or isolated restore drills. Keep old backup keys until all archives encrypted with them expire or are re-encrypted and restore-tested.

Follow `docs/BACKUP-RESTORE-RUNBOOK.md` for destructive restore procedure, RPO/RTO evidence, integrity verification, and recovery validation.

## Observability and SLOs

The `observability` profile is local and optional. Telemetry exporter failure does not take down core retrieval. Metrics/traces must not contain API keys, bearer tokens, cookies, passwords, provider credentials, or raw document text by default.

Grafana anonymous access is disabled. Set the operator-controlled Grafana Admin secret before using the profile.

Initial SLO objectives and metric names are documented in `docs/OBSERVABILITY-SLO.md`. Treat them as calibration targets until real production workload data establishes the deployment-specific baseline.

## Security release checks

Before a production tag, require green evidence for:

- backend Ruff and full pytest suite
- real Postgres integration
- real Qdrant lifecycle and tenant-negative tests
- frontend auth/OIDC tests and Next.js production build
- Compose default/HA/security/observability/ops/combined validation
- ClamAV fail-closed and PDF active-content regression coverage
- scoped-key authorization and cross-tenant negative coverage
- representative service-API E2E
- destructive backup/restore drill
- bounded performance validation
- backend dependency audit, frontend production dependency audit, full-history secret scan, and pull-request dependency review

A failed or unavailable required release gate is a release blocker; do not weaken the gate or mark it complete from intent alone.

## Upgrade procedure

For a routine production upgrade:

1. Read release notes and migration notes before changing images/source.
2. Create and verify a backup; for sensitive portable backups require encryption.
3. Record current application, Qdrant, Postgres/SQLite, and model versions.
4. Stop mutating traffic or enter the documented maintenance boundary when a migration/restore-sensitive change requires it.
5. Deploy the new version using the same secret/tenant configuration.
6. Validate `/api/v1/health`, Admin authentication, tenant-scoped search/query, ingestion, queue processing, and observability.
7. Confirm a retrieval-only zworkforce integration call if the consumer is deployed.
8. Keep the prior image/tag and backup available until rollback criteria expire.

## Rollback criteria

Rollback when a release causes authentication/authorization regression, cross-tenant visibility, persistent ingestion failure, retrieval correctness failure, destructive lifecycle regression, backup incompatibility, or SLO-impacting errors beyond the operator's accepted threshold.

Application rollback does not automatically undo data mutations. If data restoration is required, use the destructive restore runbook and retain the automatic pre-restore safety backup.

## Final-release boundary

A production tag may be created only after `exec-planning.md` release evidence is complete and the governed zworkforce consumer integration has passed its own branch-protection/reviewer policy. Release documentation must record the final zknowbase main SHA, zworkforce consumer SHA, version/tag, CI/security evidence, known limitations, and rollback/restore references.
