# Encryption policy

zknowbase remains local-first. Encryption and tenant authorization are separate controls.

## Portable backups

When `ZKB_BACKUP_ENCRYPTION_KEY_FILE` is configured, backup exports use an authenticated AES-256-GCM envelope and the `.zkb` extension. Encryption and decryption stream data in bounded chunks. Restore and verify authenticate the envelope before parsing archive members or changing application state.

Set `ZKB_BACKUP_REQUIRE_ENCRYPTION=true` for deployments where plaintext backup exports must be rejected. The configured key file must contain base64 encoding of exactly 32 random bytes and must be restricted to its owner on POSIX systems. The key is not stored in the backup archive.

For rotation, switch future backups to a newly generated key, retain the previous key until all archives that require it have expired or been replaced, verify a new archive, perform an isolated restore drill, and only then retire the old key.

## Runtime secrets

Service API key material is stored as digests rather than plaintext. Admin session secrets, identity-provider client secrets, and optional provider API keys remain runtime configuration and must not be exposed to browser code.

## Live data at rest

SQLite, uploaded source files, Qdrant data, and self-hosted Postgres data remain on operator-controlled volumes. Production deployments should protect those volumes with established platform or database encryption rather than custom application-layer field cryptography, so indexing, tenant filtering, retrieval, and recovery semantics remain intact.

Use TLS whenever application or database traffic crosses an untrusted network boundary.

## Tenant recovery

Encrypted storage does not replace tenant checks. Authenticated principals, service-key ownership, document ownership, ingestion-job ownership, Qdrant payload filters, and audit ownership remain authoritative. Postgres backup and restore preserve the tenant mapping tables; legacy format-version 1 archives without those tables retain the documented default-tenant migration behavior.

## Release verification

A production release should prove that an encrypted backup verifies and restores with the correct key, fails with a different key, fails after ciphertext modification, rejects plaintext when encryption is required, and keeps the key file and exported archive restricted from group/world access on POSIX systems.
