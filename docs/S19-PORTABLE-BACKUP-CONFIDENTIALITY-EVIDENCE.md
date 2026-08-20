# S19 Portable Backup Confidentiality Evidence

This document records immutable evidence for the `exec-planning.md` S19 native portable-backup confidentiality slice. It does not weaken or replace the implementation, CI, Security, tenant-isolation, or disaster-recovery requirements inherited from S1-S18.

## Implementation boundary

The native portable backup envelope is implemented in `backend/app/backup_crypto.py` using the reviewed `cryptography` package and AES-256-GCM. The envelope is versioned (`ZKB-AESGCM-v1`), uses a fresh 96-bit nonce per archive, authenticates fixed additional data, uses a 128-bit GCM tag, and processes payloads in bounded 1 MiB chunks.

Backup keys are loaded only from an operator-controlled key file. The file must contain strict base64 for exactly 32 bytes and, on POSIX systems, fails closed when group/world permission bits are present. Keys are not embedded in archives or exposed through browser configuration.

Encrypted outputs and temporary authenticated-decryption outputs are created atomically with owner-only `0600` permissions from the first filesystem create operation, independent of process `umask`.

Decryption authenticates the complete envelope before archive extraction or destructive restore mutation. Partial plaintext output is removed when authentication/decryption fails.

## Negative security behavior

Regression coverage associated with S19 proves fail-closed behavior for:

- wrong backup key;
- modified/tampered ciphertext;
- truncated encrypted envelope;
- insecure key-file permissions;
- plaintext archives when encryption is required;
- permissive process `umask` attempting to broaden encrypted/decrypted output permissions.

The truncation regression mutates live metadata and uploaded-file state after backup creation and verifies that a truncated archive cannot restore metadata, overwrite the upload sentinel, or invoke Qdrant restore before authenticated decryption succeeds.

## Compatibility and tenant ownership

S19 does not change the service API, SDK API, or the local-first deployment architecture. Plain legacy portable archives remain supported only when the operator has not enabled the require-encryption policy.

Current Postgres backup/restore retains the tenant ownership sidecars for service keys, ingestion jobs, and immutable audit records. Legacy format-version 1 archives retain the explicit deterministic fallback policy documented by the existing DR implementation.

## Key rotation, escrow, and retention

`docs/ENCRYPTION-POLICY.md` defines the operator-owned key boundary and requires old decryption keys to be retained for as long as any dependent historical archive or legal-hold recovery point remains recoverable. Creating a new backup from current live state does not replace a historical recovery point.

A prior key may be destroyed only after every dependent archive/recovery obligation expires, or after the exact historical archive has undergone a content-preserving re-encryption procedure that is independently verified and restore-drilled under the replacement key. Until such a workflow is implemented, retained archives require independently protected escrow copies of their original key generation.

## Immutable PR and workflow evidence

S19 completion work was merged through PR #54, `security: complete S19 backup confidentiality evidence`.

- PR head: `53eec0ca547c126a1a4b49a8321b64e2b3a2ee86`
- merge commit: `53ae26c6086525f0e03131a1cbbce62024876bc0`
- exact-head CI: run `32361797503`, CI #156, `success`
- exact-head Security: run `32361797482`, Security #36, `success`

The PR was merged only after its correctness review was repaired so the truncation test demonstrated pre-mutation failure and the retention policy preserved historical recovery points.

## S19 acceptance conclusion

The repository evidence supports the S19 acceptance statement: encrypted portable archives do not expose plaintext knowledge content at rest through the application backup format; wrong-key, tamper, and truncation restore attempts fail before application restore mutation; encryption remains self-hosted with bounded resource usage; and the existing SQLite/Postgres disaster-recovery contract remains intact.
