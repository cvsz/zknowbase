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
| Knowledge content | uploads, extracted metadata, SQLite/Postgres rows, Qdrant vectors/payloads | Production deployments containing sensitive data must use host/filesystem/volume encryption. zknowbase does not claim application-level encryption for arbitrary live document fields. | TLS whenever traffic crosses a host trust boundary. |
| Tenant ownership/audit metadata | tenant IDs, service-key mappings, ingestion-job mappings, audit ownership | Protected by the same encrypted metadata volume/database storage as other metadata. | TLS whenever traffic crosses a host trust boundary. |
| Backups | metadata, uploads, Qdrant snapshots | zknowbase can wrap portable archives in an authenticated AES-256-GCM envelope using an operator-owned local key. Production may fail closed on plaintext backups with `ZKB_BACKUP_REQUIRE_ENCRYPTION=true`. | Use authenticated encrypted transport when copying backups. |

## Approved cryptography

zknowbase does not define proprietary encryption algorithms or custom cryptographic constructions.

Current application cryptography/security primitives include:

- `scrypt` for local Admin password hashing.
- HMAC-signed Admin session state using the configured session secret.
- SHA-256 digests for generated high-entropy service-key verification and backup integrity manifests.
- AES-256-GCM for optional authenticated portable-backup encryption, implemented through the `cryptography` package with a fresh 96-bit nonce and fixed versioned additional authenticated data for every archive.
- OIDC Authorization Code flow with PKCE for optional self-hosted identity-provider login.
- TLS termination supplied by the deployment boundary for traffic leaving a trusted local development boundary.

For live storage encryption, operators must use established platform mechanisms such as LUKS/dm-crypt, encrypted VM disks, encrypted ZFS datasets, BitLocker-backed host volumes where applicable, or an equivalent reviewed filesystem/block-device mechanism. Database-native encryption may be used when it is self-hosted and operationally managed, but it does not replace filesystem protection for uploaded files and live Qdrant storage.

## Backup encryption envelope

When `ZKB_BACKUP_ENCRYPTION_KEY_FILE` is configured, `zknowbase backup` writes a `.zkb` envelope instead of a plaintext `.tar.gz` archive. The key file contains strict base64 encoding of exactly 32 random bytes. On POSIX platforms it must not be group/world accessible. The envelope uses:

- AES-256-GCM;
- a fresh 12-byte nonce for every archive;
- versioned magic and additional authenticated data;
- bounded 1 MiB streaming encryption/decryption;
- the GCM authentication tag to reject wrong keys, modification, or truncation before archive parsing or restore mutation.

`ZKB_BACKUP_REQUIRE_ENCRYPTION=true` rejects plaintext backup verification/restore and is invalid unless a backup key file is configured. When encryption is configured, pre-restore safety backups use the same encrypted envelope. The encryption key is never embedded in the archive.

## Key ownership

The deployment operator owns all encryption and authentication key material. zknowbase must not silently create a hosted dependency for key custody.

Production requirements:

1. `ZKB_API_KEY` must be replaced before startup and the bootstrap key should be disabled after scoped service keys are provisioned.
2. `ZKB_ADMIN_SESSION_SECRET` must be high entropy and stored outside source control.
3. Optional provider/OIDC secrets must remain server-side and must never be exposed through `NEXT_PUBLIC_*`, browser payloads, logs, audit detail, or telemetry.
4. Host/volume encryption keys must be managed separately from the data they protect and must be recoverable under the organization's disaster-recovery procedure.
5. `ZKB_BACKUP_ENCRYPTION_KEY_FILE` must be mounted from operator-controlled secret storage, kept separate from backup archives, and included in recovery-key escrow/rotation procedures.

## Rotation

- Service keys: rotate with the service-key lifecycle API; rotation atomically revokes the old credential while preserving tenant ownership.
- Bootstrap API key: rotate through deployment secret management, validate replacement access, then restart/redeploy; disable bootstrap mode after provisioning where practical.
- Admin session secret: changing it intentionally invalidates all active Admin sessions. Coordinate rotation as an authentication maintenance event.
- OIDC/provider secrets: rotate at the provider and deployment secret boundary; never commit replacement values.
- Storage/volume keys: use the host platform's supported rekey procedure and validate both normal startup and restore before retiring old recovery material.
- Backup encryption keys: retain old decryption material until every `.zkb` archive encrypted with it has expired or has been decrypted and re-encrypted with the replacement key, and restore-test at least one resulting archive before retiring the old key.

## Backup and disaster recovery

The native backup path provides integrity manifests, safe extraction checks, owner-only archive permissions, pre-restore safety backup, tenant-mapping preservation, Qdrant version compatibility checks, and optional authenticated AES-256-GCM confidentiality.

Production guidance:

- Set `ZKB_BACKUP_ENCRYPTION_KEY_FILE` to an owner-only local secret file for portable backups containing sensitive data.
- Set `ZKB_BACKUP_REQUIRE_ENCRYPTION=true` when policy requires fail-closed rejection of plaintext archives.
- Keep the encryption key independent from the backup archive and test recovery-key availability during DR drills.
- Existing plaintext archives remain supported only when encryption is not required, preserving local-development and legacy restore compatibility.
- Losing the encryption key is an availability failure; exposing it is a confidentiality incident and requires key rotation according to archive retention scope.

## Logging and telemetry

Logs, audit records, metrics, and traces must not contain API keys, raw bearer tokens, passwords, Admin cookies/session secrets, OIDC tokens, cloud-provider credentials, backup encryption keys, or document body text by default. Tenant IDs and opaque resource IDs may be recorded when required for authorization/audit attribution.

## Non-claims

zknowbase currently does not claim:

- field-level encryption of arbitrary live document metadata;
- application-layer encryption of live Qdrant vectors or uploaded document bytes;
- transparent database encryption supplied by zknowbase itself;
- protection from an attacker who has both a `.zkb` archive and its encryption key.

These are deliberate boundaries, not hidden guarantees. Deployments that require cryptographic separation even from the host/storage administrator need an additional envelope/field-encryption design and key-management threat model before that capability can be claimed.

## Release evidence

A release may claim this policy is implemented only when:

- tenant isolation tests remain green for SQLite/Postgres/Qdrant/async/audit paths;
- generated service-key plaintext is not persisted;
- local Admin password/session boundaries remain tested;
- backup/restore preserves tenant ownership and archive integrity;
- encrypted backup round-trip, wrong-key, tamper, plaintext-policy, and key-permission regression tests are green;
- production documentation explicitly requires encrypted storage for sensitive live data and encrypted transport outside trusted local development boundaries;
- no documentation claims field/live-vector encryption that the source code does not provide.
