# zknowbase Encryption Policy

## Scope

This policy defines the cryptographic and storage-encryption boundary for self-hosted zknowbase. It preserves the local-first / zero recurring API cost architecture: no hosted KMS, managed database, or paid security service is required.

## Tenant isolation and storage model

zknowbase uses a shared Qdrant collection with mandatory server-side `tenant_id` payload enforcement. Tenant identity comes from the authenticated service principal and propagates through metadata, synchronous and asynchronous ingestion, queue ownership, vector operations, service-key lifecycle, and immutable security-audit ownership. Client-supplied filters cannot replace or override this boundary.

SQLite and Postgres metadata rows carry or join to durable tenant ownership. Postgres tenant sidecar tables are part of the backup/restore contract. Qdrant snapshots preserve tenant payloads with the collection snapshot.

## Classification and required protection

| Data class | At-rest control | In-transit control |
| --- | --- | --- |
| Authentication/session/provider secrets | Operator-controlled environment or secret files; never source control or browser payloads. | TLS outside trusted local development boundaries. |
| Generated service keys | zknowbase persists SHA-256 digests only; plaintext is returned only at create/rotate time. | TLS outside trusted local development boundaries. |
| Admin passwords | scrypt hashes only. | TLS outside trusted local development boundaries. |
| Knowledge content, SQLite, Qdrant, uploads | Production deployments use established host/filesystem/volume encryption. zknowbase does not claim arbitrary field-level document encryption. | TLS across host trust boundaries. |
| Tenant/audit metadata | Same encrypted metadata storage boundary as other metadata. | TLS across host trust boundaries. |
| Portable native backups | Optional native streaming AES-256-GCM authenticated envelope; production policy can reject plaintext exports/restores. | Authenticated encrypted transport when copied. |

## Native backup envelope

When `ZKB_BACKUP_ENCRYPTION_KEY_FILE` is configured, native backup exports use the `.zkb` envelope. The implementation uses AES-256-GCM from the reviewed `cryptography` library, a fresh 96-bit nonce for each archive, fixed versioned additional authenticated data, a 128-bit authentication tag, and bounded 1 MiB streaming chunks.

The key file contains strict base64 encoding of exactly 32 bytes. On POSIX systems it must not be group/world accessible. The key is never embedded in the archive. Decryption authenticates the complete encrypted envelope before tar extraction or restore mutation, and partial decrypted output is removed on failure.

`ZKB_BACKUP_REQUIRE_ENCRYPTION=true` makes plaintext backup verification and restore fail closed. When encryption is configured, pre-restore safety backups are encrypted as well. Plain `.tar.gz` archives remain supported when the required-encryption policy is disabled so local development and existing archives remain compatible.

## Approved cryptography

zknowbase does not define proprietary encryption algorithms. Application security primitives include:

- scrypt for local Admin password hashing;
- HMAC-signed Admin session state;
- SHA-256 service-key digests and backup integrity manifests;
- AES-256-GCM for optional native backup confidentiality and authenticated integrity;
- OIDC Authorization Code with PKCE for optional self-hosted identity login;
- deployment TLS for traffic leaving trusted local development boundaries.

Live SQLite, Qdrant, Postgres, and upload storage should use established platform controls such as LUKS/dm-crypt, encrypted VM disks, encrypted ZFS datasets, BitLocker-backed host volumes where applicable, or equivalent reviewed storage encryption. This avoids inventing field cryptography that would undermine indexing, filtering, retrieval, and database recovery semantics.

## Key ownership and rotation

The deployment operator owns all encryption and authentication key material. Backup encryption keys are supplied from an operator-controlled local file and are not silently delegated to a hosted dependency.

For backup-key rotation: generate a replacement 256-bit key, switch future backups to it, retain prior decryption material until all matching archives expire or are recreated, verify the new backup, complete an isolated restore drill, and only then retire the old key. Loss of required decryption material is an availability failure; disclosure requires rotation and incident handling for the affected archive scope.

### Escrow and retention

Production operators should maintain at least one independently protected recovery copy of every backup key that is still required by retained archives. The escrow copy must stay outside the zknowbase repository, browser/client configuration, backup archive, and ordinary application data volume. Acceptable self-hosted boundaries include an offline encrypted removable medium, a separately administered encrypted host/volume, or an operator-controlled secret manager that does not introduce a mandatory hosted dependency.

Each retained archive must have an operator record mapping it to the key generation that can decrypt it. Retention policy must keep that key generation available for at least as long as any corresponding archive, legal hold, or recovery objective requires. Before destroying an old key, operators must either expire all dependent archives or re-create and verify replacements under the new key, then perform an isolated restore drill. Key escrow copies should be access-controlled, periodically inventoried, and recovery-tested without exposing key material in logs, tickets, CI artifacts, or telemetry.

Service-key, bootstrap-key, Admin-session, OIDC/provider, and storage-volume key rotation remain governed by their respective deployment boundaries.

## Backup and disaster recovery

Native backup/restore provides manifest integrity checks, safe extraction, owner-only archive permissions, pre-restore safety backup, tenant-mapping preservation, Qdrant compatibility checks, and optional authenticated encryption. Current Postgres backups preserve `service_key_tenants`, `ingestion_job_tenants`, and `security_audit_tenants`. Legacy format-version 1 archives without those sidecars retain deterministic fallback behavior.

Production restore drills should prove the archive, encryption key, tenant ownership, metadata, uploads, and Qdrant snapshot can all be restored together.

## Logging and telemetry

Logs, audit records, metrics, and traces must not contain API keys, bearer tokens, passwords, Admin cookies/session secrets, OIDC tokens, provider credentials, backup keys, or document body text by default. Tenant IDs and opaque resource IDs may be recorded when needed for authorization and operations.

## Non-claims

zknowbase does not claim field-level encryption of arbitrary document metadata, application-layer encryption of Qdrant vectors, or application-layer encryption of live uploaded document bytes. Deployments needing cryptographic separation from the host/storage administrator require a separate envelope/field-encryption threat model and key-management design.

## Release evidence

A release may claim this policy is implemented only when tenant-isolation gates remain green, service-key plaintext is not persisted, Admin/OIDC boundaries remain tested, native encrypted backup positive/negative tests pass, Postgres DR preserves tenant sidecars, and documentation does not claim cryptographic protection absent from source code.
