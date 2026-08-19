# Security Policy

## Supported versions

Security fixes are provided for the current `main` branch and the latest tagged production release. Older tags are not guaranteed to receive backports unless a release advisory explicitly says otherwise.

## Reporting a vulnerability

Do not disclose a suspected vulnerability in a public issue before maintainers have had an opportunity to assess it. Use GitHub's private vulnerability reporting/security-advisory channel for this repository when available. Include the affected commit/tag, reproduction steps, impact, required privileges, and any evidence needed to validate the finding without including unrelated secrets or private data.

If private reporting is unavailable, contact the repository owner through a private channel and reference `cvsz/zknowbase` without publishing exploit details.

## Security boundaries

zknowbase is designed as a self-hosted, local-first knowledge service. The supported security model requires:

- authentication on protected `/api/v1/*` endpoints;
- scoped, revocable service keys whose plaintext is never persisted by zknowbase;
- tenant identity derived from the authenticated principal, not from caller-supplied filters;
- tenant enforcement across document metadata, ingestion jobs, Qdrant payload operations, service-key administration, and security-audit reads;
- local Admin authentication/RBAC or optional self-hosted OIDC with Authorization Code + PKCE;
- upload validation before parsing, with optional local ClamAV that fails closed when configured;
- SSRF-resistant URL ingestion and bounded response/upload sizes;
- server-side service credentials that are never exposed to browser JavaScript;
- integrity-checked, owner-only backup archives with tenant ownership preserved across supported restore paths;
- optional native AES-256-GCM authenticated encryption for portable backup archives, with fail-closed enforcement when `ZKB_BACKUP_REQUIRE_ENCRYPTION=true`;
- local metrics/traces that exclude secrets and raw document contents by default.

See `docs/ENCRYPTION-POLICY.md` for the at-rest/in-transit encryption boundary, key ownership, rotation, and explicit non-claims.

## Deployment requirements

The default Compose stack is intended to run without paid SaaS, but production hardening remains the operator's responsibility at the host/network boundary. Sensitive production deployments must use encrypted host/filesystem/volume storage and TLS whenever traffic crosses a trusted local development boundary.

Native portable backups can be application-encrypted by mounting an owner-only key file containing base64 for exactly 32 random bytes and setting `ZKB_BACKUP_ENCRYPTION_KEY_FILE`. Production deployments that require portable-backup confidentiality should also set `ZKB_BACKUP_REQUIRE_ENCRYPTION=true`; plaintext archives are then rejected by verify/restore. The backup key must be stored separately from the archive and retained for the lifetime of backups encrypted with it. Native backup encryption does not replace host/volume encryption for live SQLite/Postgres/Qdrant/upload data.

Secrets must not be committed to the repository. Replace default bootstrap material, configure a high-entropy Admin session secret, restrict `.env`/secret-file permissions, and disable the bootstrap API key after scoped keys are provisioned where practical. Browser/static configuration must never contain zknowbase service credentials.

The optional observability profile keeps Grafana anonymous access disabled and requires an operator-controlled `ZKB_GRAFANA_ADMIN_PASSWORD`. Prometheus/Grafana bind to loopback in the supplied Compose profile; expose them remotely only behind an authenticated/TLS-protected operator boundary.

## Dependency and secret scanning

Release CI performs independent production dependency and secret gates:

- PyPA `pip-audit` against pinned backend production requirements;
- `npm audit --omit=dev --audit-level=high` against the frontend production dependency graph;
- GitHub Dependency Review for newly introduced high/critical dependency findings;
- full-history Gitleaks scanning using the repository policy in `.gitleaks.toml`.

The Gitleaks policy contains only a narrow historical allowlist for a deterministic Admin-session-secret value that existed exclusively in a unit-test fixture. Current tests generate that value randomly. Broad path/rule suppressions are not part of the release policy.

## Incident response

For a suspected credential compromise, revoke/rotate affected service keys immediately, rotate deployment/provider/OIDC secrets according to their ownership boundary, invalidate Admin sessions by rotating the session secret when necessary, and preserve relevant audit evidence. For a storage-encryption key compromise, follow the storage platform's rekey procedure and treat exposed backups/volumes as potentially disclosed according to the data classification in `docs/ENCRYPTION-POLICY.md`.

For a portable-backup key compromise, retain affected archives as potentially disclosed, generate a replacement key, create and verify new encrypted backups, complete a restore drill with the replacement key, and keep old decryption material only as long as required to recover retained historical archives.

## Security acceptance

A change is not considered production-ready merely because it builds. Required security regression coverage includes authentication/authorization failures, tenant-isolation negative cases, upload active-content rejection, configured ClamAV fail-closed behavior, OIDC state/PKCE validation, scoped-key lifecycle behavior, backup/restore ownership preservation, dependency audit gates, and full-history secret scanning where applicable.
