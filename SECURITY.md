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
- tenant identity derived from the authenticated principal, not from caller-supplied filters or governed-context metadata;
- tenant enforcement across document metadata, ingestion jobs, Qdrant payload operations, service-key administration, and security-audit reads;
- local Admin authentication/RBAC or optional self-hosted OIDC with Authorization Code + PKCE;
- upload validation before parsing, with optional local ClamAV that fails closed when configured;
- SSRF-resistant URL ingestion and bounded response/upload sizes;
- server-side service credentials that are never exposed to browser JavaScript;
- integrity-checked backups with tenant ownership preserved across supported restore paths;
- optional authenticated AES-256-GCM encryption for portable native backups;
- local observability that excludes secrets and raw document contents by default.

See `docs/ENCRYPTION-POLICY.md` for the at-rest/in-transit encryption boundary, key ownership, rotation, and explicit non-claims. See `docs/PRODUCTION-DEPLOYMENT.md` for the supported deployment, network, upgrade, rollback, and release boundary.

## Deployment requirements

The default Compose stack is intended to run without paid SaaS, but production hardening remains the operator's responsibility at the host/network boundary. Sensitive production deployments must use encrypted host/filesystem/volume storage and TLS whenever traffic crosses a trusted local development boundary.

Native zknowbase backups can use an authenticated AES-256-GCM envelope when `ZKB_BACKUP_ENCRYPTION_KEY_FILE` is configured. Set `ZKB_BACKUP_REQUIRE_ENCRYPTION=true` for deployments that must reject plaintext backup verify/restore. Backup encryption does not replace encrypted live volumes, tenant authorization, key escrow, retention policy, or restore drills.

Secrets must not be committed to the repository. Replace default bootstrap material, configure a high-entropy Admin session secret, restrict `.env`/secret-file permissions, and disable the bootstrap API key after scoped keys are provisioned where practical. Keep Qdrant, Ollama, Postgres, ClamAV, metrics, and collector endpoints on trusted/internal networks unless a reviewed deployment explicitly protects them.

## Consumer boundary

`cvsz/zworkforce` and other consumers must use zknowbase only through the authenticated service API/SDK. Retrieval-only consumers should receive tenant-bound `knowledge:read` credentials. Agent/browser code must never receive a zknowbase service key or connect directly to Qdrant.

Governed zworkforce context supplies actor/agent/tool/policy/request/trace correlation, but it cannot override the tenant attached to the authenticated zknowbase principal. Missing, malformed, request-ID-inconsistent, or cross-tenant governed context fails closed when the governed context contract is used.

## Incident response

For a suspected credential compromise, revoke/rotate affected service keys immediately, rotate deployment/provider/OIDC secrets according to their ownership boundary, invalidate Admin sessions by rotating the session secret when necessary, and preserve relevant audit evidence.

For a backup-encryption key compromise, treat retained archives encrypted with that key as potentially disclosed, rotate to a new key for future backups, retain old material only as needed for recovery of affected retained archives, and follow the organization's incident/retention policy.

For a storage-encryption key compromise, follow the storage platform's rekey procedure and treat exposed backups/volumes as potentially disclosed according to the data classification in `docs/ENCRYPTION-POLICY.md`.

For suspected cross-tenant access, preserve security audit records and request/trace IDs, revoke affected credentials if necessary, and treat the incident as an authorization-boundary failure until negative isolation tests and production evidence establish containment.

## Security acceptance

A change is not considered production-ready merely because it builds. Required security regression coverage includes authentication/authorization failures, tenant-isolation negative cases, upload active-content rejection, configured ClamAV fail-closed behavior, OIDC state/PKCE validation, scoped-key lifecycle behavior, backup/restore ownership preservation, and governed consumer tenant binding where applicable.

Final production releases additionally require green dependency vulnerability checks, full-history committed-secret scanning under the repository's narrow reviewed policy, representative E2E evidence, DR evidence, and branch-protected consumer integration evidence. Required checks must not be weakened or bypassed to declare a release complete.
