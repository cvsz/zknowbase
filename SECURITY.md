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
- optional native AES-256-GCM authenticated encryption for portable backup archives using an operator-owned local key file;
- local observability that does not require hosted SaaS and does not record secrets or document body text by default.

See `docs/ENCRYPTION-POLICY.md` for the at-rest/in-transit encryption boundary, backup-envelope key ownership and rotation, and explicit non-claims. See `docs/OBSERVABILITY-SLO.md` for the telemetry and SLO boundary.

## Deployment requirements

The default Compose stack is intended to run without paid SaaS, but production hardening remains the operator's responsibility at the host/network boundary. Sensitive production deployments must use encrypted host/filesystem/volume storage and TLS whenever traffic crosses a trusted local development boundary.

Native backup archives support an authenticated AES-256-GCM envelope when `ZKB_BACKUP_ENCRYPTION_KEY_FILE` is configured. Production deployments that require encrypted portable backups should also set `ZKB_BACKUP_REQUIRE_ENCRYPTION=true`; plaintext archives are then rejected by verify/restore. The backup key must be stored separately from backup archives, restricted to the service/operator account, retained for the lifetime of archives encrypted with it, and included in disaster-recovery escrow/rotation procedures. Native backup encryption protects portable archives; it does not replace host/volume encryption for live SQLite/Postgres data, uploaded documents, or Qdrant storage.

Secrets must not be committed to the repository. Replace default bootstrap material, configure a high-entropy Admin session secret, restrict `.env`/secret-file permissions, and disable the bootstrap API key after scoped keys are provisioned where practical. Grafana in the optional observability profile requires operator-controlled local admin credentials and does not permit anonymous access.

## zworkforce consumption boundary

`cvsz/zworkforce` must consume zknowbase only through the authenticated service API/client boundary. Retrieval consumers use least-privilege `knowledge:read` service credentials bound to the expected tenant. Governed execution metadata may improve audit correlation but cannot override the tenant attached to the authenticated zknowbase principal. Agents must never connect directly to Qdrant or receive zknowbase service credentials in browser/client code.

## Incident response

For a suspected credential compromise, revoke/rotate affected service keys immediately, rotate deployment/provider/OIDC secrets according to their ownership boundary, invalidate Admin sessions by rotating the session secret when necessary, and preserve relevant audit evidence. For a backup-key compromise, generate a replacement key, create and verify new encrypted backups, retain the old key only as long as required to restore archives encrypted with it, and treat exposed archives as potentially disclosed according to the data classification in `docs/ENCRYPTION-POLICY.md`. For a live storage-encryption key compromise, follow the storage platform's rekey procedure.

## Security acceptance

A change is not considered production-ready merely because it builds. Required security regression coverage includes authentication/authorization failures, tenant-isolation negative cases, upload active-content rejection, configured ClamAV fail-closed behavior, OIDC state/PKCE validation, scoped-key lifecycle behavior, backup/restore ownership preservation, encrypted-backup tamper/wrong-key rejection where configured, dependency vulnerability gates, and committed-secret scanning.
