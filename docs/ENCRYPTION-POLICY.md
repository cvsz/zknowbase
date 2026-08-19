# zknowbase Encryption Policy

## Scope

This policy defines the cryptographic and storage-encryption boundary for the self-hosted zknowbase runtime. It is intentionally compatible with the local-first / zero recurring API cost architecture: no hosted KMS, managed database, or paid security service is required.

## Tenant isolation and storage model

zknowbase uses a shared Qdrant collection with mandatory server-side `tenant_id` payload enforcement rather than one collection per tenant. Tenant identity comes from the authenticated service principal and is propagated through document metadata, synchronous and asynchronous ingestion, queue ownership, vector upsert/search/delete, service-key lifecycle, and security audit ownership. Client-supplied filters cannot replace or override this boundary.

SQLite and Postgres metadata rows carry or are joined to durable tenant ownership. Tenant mapping tables are part of the backup/restore contract. Qdrant snapshots preserve tenant payloads because they snapshot the collection itself.

## Classification and required protection

| Data class | Examples | At-rest requirement | In-transit requirement |
| --- | --- | --- | --- |
| Authentication secrets | bootstrap key, Admin session secret, optional cloud API keys, OIDC client secret | Must never be committed. Store only in operator-controlled environment/secret files with restrictive permissions; production host/volume encryption is required. | TLS outside loopback/private trusted development boundaries. |
| Service keys | generated `zkb_*` bearer credentials | Plaintext is returned only at creation/rotation and must not be persisted by zknowbase. zknowbase stores SHA-256 digests only. | TLS outside loopback/private trusted development boundaries. |
| Admin passwords | local human credentials | scrypt password hashes only; plaintext passwords are not persisted. | TLS outside loopback/private trusted development boundaries. |
| Knowledge content | uploads, extracted metadata, SQLite/Postgres rows, Qdrant vectors/payloads | Production deployments containing sensitive data must use host/filesystem/volume encryption. zknowbase does not claim application-level encryption for arbitrary document fields. | TLS whenever traffic crosses a host trust boundary. |
| Tenant ownership/audit metadata | tenant IDs, service-key mappings, ingestion-job mappings, audit ownership | Protected by the same encrypted metadata volume/database storage as other metadata. | TLS whenever traffic crosses a host trust boundary. |
| Backups | metadata, uploads, Qdrant snapshots | Backup archives are integrity-protected by SHA-256 manifests and owner-only permissions, but the current archive format is not application-encrypted. Sensitive backups MUST additionally be stored on encrypted media or wrapped by an operator-approved standard encryption tool before leaving the trusted host. | Use authenticated encrypted transport when copying backups. |

## Approved cryptography

zknowbase does not define proprietary encryption algorithms or custom cryptographic constructions.

Current application cryptography/security primitives include:

- `scrypt` for local Admin password hashing.
- HMAC-signed Admin session state using the configured session secret.
- SHA-256 digests for generated high-entropy service-key verification and backup integrity manifests.
- OIDC Authorization Code flow with PKCE for optional self-hosted identity-provider login.
- TLS termination supplied by the deployment boundary for traffic leaving a trusted local development boundary.

For storage encryption, operators must use established platform mechanisms such as LUKS/dm-crypt, encrypted VM disks, encrypted ZFS datasets, BitLocker-backed host volumes where applicable, or an equivalent reviewed filesystem/block-device mechanism. Database-native encryption may be used when it is self-hosted and operationally managed, but it does not replace filesystem/backup protection for uploaded files and Qdrant snapshots.

## Key ownership

The deployment operator owns all encryption and authentication key material. zknowbase must not silently create a hosted dependency for key custody.

Production requirements:

1. `ZKB_API_KEY` must be replaced before startup and the bootstrap key should be disabled after scoped service keys are provisioned.
2. `ZKB_ADMIN_SESSION_SECRET` must be high entropy and stored outside source control.
3. Optional provider/OIDC secrets must remain server-side and must never be exposed through `NEXT_PUBLIC_*`, browser payloads, logs, audit detail, or telemetry.
4. Host/volume encryption keys must be managed separately from the data they protect and must be recoverable under the organization's disaster-recovery procedure.
5. Backup encryption keys, when backups leave encrypted trusted storage, must be retained independently from the backup archive and included in recovery-key escrow/rotation procedures.

## Rotation

- Service keys: rotate with the service-key lifecycle API; rotation atomically revokes the old credential while preserving tenant ownership.
- Bootstrap API key: rotate through deployment secret management, validate replacement access, then restart/redeploy; disable bootstrap mode after provisioning where practical.
- Admin session secret: changing it intentionally invalidates all active Admin sessions. Coordinate rotation as an authentication maintenance event.
- OIDC/provider secrets: rotate at the provider and deployment secret boundary; never commit replacement values.
- Storage/volume keys: use the host platform's supported rekey procedure and validate both normal startup and restore before retiring old recovery material.
- Backup wrapping keys: retain old decryption material until every archive encrypted with it has expired or been re-encrypted and restore-tested.

## Backup and disaster recovery

The native backup archive currently provides integrity verification, safe extraction checks, owner-only file permissions, pre-restore safety backup, tenant-mapping preservation, and Qdrant version compatibility checks. It does **not** claim confidentiality by itself.

Therefore:

- A backup remaining exclusively on an encrypted trusted volume is covered by the volume-encryption boundary.
- A backup copied off that boundary must first be encrypted with an operator-approved standard tool or placed into equivalently encrypted storage.
- Restore drills must include availability of encryption/recovery keys in addition to zknowbase archive integrity checks.
- Losing storage or backup encryption keys is an availability failure; exposing them is a confidentiality incident and requires credential/key rotation according to the affected scope.

## Logging and telemetry

Logs, audit records, metrics, and traces must not contain API keys, raw bearer tokens, passwords, Admin cookies/session secrets, OIDC tokens, cloud-provider credentials, or document body text by default. Tenant IDs and opaque resource IDs may be recorded when required for authorization/audit attribution.

## Non-claims

zknowbase currently does not claim:

- field-level encryption of arbitrary document metadata;
- application-layer encryption of Qdrant vectors or uploaded document bytes;
- transparent database encryption supplied by zknowbase itself;
- application-encrypted native backup archives.

These are deliberate boundaries, not hidden guarantees. Deployments that require cryptographic separation even from the host/storage administrator need an additional envelope/field-encryption design and key-management threat model before that capability can be claimed.

## Release evidence

A release may claim this policy is implemented only when:

- tenant isolation tests remain green for SQLite/Postgres/Qdrant/async/audit paths;
- generated service-key plaintext is not persisted;
- local Admin password/session boundaries remain tested;
- backup/restore preserves tenant ownership and archive integrity;
- production documentation explicitly requires encrypted storage for sensitive at-rest data and encrypted transport outside trusted local development boundaries;
- no documentation claims application-level encryption that the source code does not provide.
