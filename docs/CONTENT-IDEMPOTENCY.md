# Content Identity and Idempotent File Ingestion

zknowbase derives uploaded-file document identity from the server-authoritative tenant and the exact uploaded bytes. The default path remains local and requires no external deduplication service.

## Identity

For an accepted file upload:

1. the upload is read within the configured size bound;
2. normal upload security/validation still runs;
3. zknowbase computes lowercase SHA-256 over the exact bytes;
4. a stable UUIDv5 document ID is derived from `tenant_id + SHA-256` using a repository-owned namespace.

The tenant comes from the authenticated service principal. A client cannot select another tenant by supplying a hash or filter. The same bytes in two different tenants therefore produce different document IDs.

The UUID namespace is a compatibility surface and must not be changed after release. SHA-256 is used only as deterministic content identity, not as a secret or password hash.

## Synchronous uploads

A repeated synchronous upload of the same validated bytes for the same tenant returns the existing non-failed document instead of parsing, embedding, or vector-upserting the content again. A failed or cancelled document may be retried using the same stable ID.

Deleting the document removes the metadata/vector/file state as before. Re-upload after an explicit delete creates the same stable ID again and runs normal ingestion; the deterministic ID does not prevent explicit lifecycle operations.

## Asynchronous uploads

A repeated asynchronous upload whose stable document already exists returns HTTP `409` before a second upload file or queue job is created. The response detail identifies the existing document and includes the non-secret `sha256:` fingerprint for operator diagnosis. Failed/cancelled documents can be retried when no active queue job owns the document.

The durable queue remains authoritative for active-job ownership. A pathological pair of requests that races before either request can observe the other's metadata may still perform redundant processing of the same deterministic document ID, but cannot create two document identities or cross tenant boundaries; normal queue/lease and vector replacement semantics converge on the same document. Eliminating even that redundant race would require a cross-store transactional idempotency ledger and is intentionally deferred rather than weakening SQLite/Postgres portability.

## URL and connector sources

URL ingestion is deliberately not content-addressed in this slice. Remote content can change at the same URL, and explicit reindex must be able to ingest a new remote version. Connector adapters should expose source/version provenance first; once a connector provides a stable source version, its idempotency key can include that version without conflating deliberate reindex with duplicate delivery.

## Security and privacy

- Upload validation is not bypassed merely because bytes were seen before.
- Document identity is always tenant-scoped.
- The fingerprint is not treated as a credential or authorization token.
- No raw document contents are added to logs or telemetry by this feature.
- No provider API, managed database, Redis, or hosted queue is introduced.
