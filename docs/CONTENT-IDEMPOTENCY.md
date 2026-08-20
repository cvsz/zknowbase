# Content Identity and Idempotent File Ingestion

zknowbase derives uploaded-file document identity from the server-authoritative tenant and the exact uploaded bytes. The default path remains local and requires no external deduplication service.

## Identity

For an accepted file upload:

1. the upload is read within the configured size bound;
2. normal upload security/validation still runs;
3. zknowbase computes lowercase SHA-256 over the exact bytes;
4. a stable UUIDv5 document ID is derived from `tenant_id + SHA-256` using a repository-owned namespace;
5. the metadata backend atomically reserves that deterministic ID before indexing or queue enqueue can begin.

The tenant comes from the authenticated service principal. A client cannot select another tenant by supplying a hash or filter. The same bytes in two different tenants therefore produce different document IDs.

The UUID namespace is a compatibility surface and must not be changed after release. SHA-256 is used only as deterministic content identity, not as a secret or password hash.

## Reservation semantics

SQLite and Postgres implement the same reservation contract without Redis or another lock service. The first request atomically inserts the deterministic document identity. A later request may take ownership only when the same tenant's existing document is in `failed` or `cancelled` state. A `processing`, `queued`, or `ready` document cannot be taken over by another request.

This metadata-store reservation is the serialization boundary for both synchronous indexing and asynchronous enqueue. It prevents two API workers from concurrently indexing the same deterministic document into separate Qdrant chunk sets, and it prevents a losing async request from deleting file/metadata state owned by the winning request.

## Synchronous uploads

A repeated synchronous upload of the same validated bytes for the same tenant returns the existing non-failed document instead of parsing, embedding, or vector-upserting the content again. Concurrent first uploads serialize through the metadata reservation, so only the reservation owner can call the indexing path. A failed or cancelled document may be retried using the same stable ID.

On retry, an existing file-backed `source_uri` is reused. This keeps one durable upload artifact for the deterministic identity even if the retry arrives under another allowed filename extension, preventing abandoned source files from accumulating.

Deleting the document removes the metadata/vector/file state as before. Re-upload after an explicit delete creates the same stable ID again and runs normal ingestion; the deterministic ID does not prevent explicit lifecycle operations.

## Asynchronous uploads

A repeated asynchronous upload whose stable document already exists returns HTTP `409` before a second upload file or queue job is created. The response detail identifies the existing document and includes the non-secret `sha256:` fingerprint for operator diagnosis. Failed/cancelled documents can be retried when no active queue job owns the document.

Concurrent first uploads serialize through the same metadata reservation. Exactly one request can own the document and proceed to write the source and enqueue a job. Cleanup is ownership-aware: if enqueue reports an error after an active job became durable, zknowbase preserves the document and source so the worker does not lose its input; otherwise only the reservation owner's still-queued state is removed.

## URL and connector sources

URL ingestion is deliberately not content-addressed in this slice. Remote content can change at the same URL, and explicit reindex must be able to ingest a new remote version. Connector adapters should expose source/version provenance first; once a connector provides a stable source version, its idempotency key can include that version without conflating deliberate reindex with duplicate delivery.

## Security and privacy

- Upload validation is not bypassed merely because bytes were seen before.
- Document identity and reservation are always tenant-scoped.
- A cross-tenant row cannot be taken over by the reservation path.
- The fingerprint is not treated as a credential or authorization token.
- No raw document contents are added to logs or telemetry by this feature.
- No provider API, managed database, Redis, or hosted queue is introduced.
