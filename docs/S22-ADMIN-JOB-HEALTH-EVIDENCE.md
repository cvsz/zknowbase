# S22 Admin Job Health Evidence

Date: 2026-08-20

This document records partial S22 evidence for tenant-safe ingestion job visibility in the Admin UI. It does not claim full S22 completion.

## Scope

The Admin UI now exposes a `Jobs` view that reads ingestion jobs through the existing same-origin Admin proxy and backend tenant-scoped `/api/v1/ingest/jobs` endpoint. The browser still never receives the backend service key; authorization remains enforced by the server-side proxy and service-key scopes.

## Operator Visibility

The page summarizes queue health by job status and shows retry pressure, attempts, lease expiry, worker identity, source type/URI, updated time, document ID, job ID, and bounded failure details. This gives operators ingestion health and failure provenance without shell or database access.

## Evidence

- `frontend/src/lib/api.ts` fetches jobs through `/api/zkb/ingest/jobs?limit=...`.
- `frontend/src/app/jobs/page.tsx` renders tenant-scoped queue health and failure/provenance details.
- `frontend/tests/admin-jobs-api.test.ts` verifies the Admin client uses the same-origin proxy path for job reads.
- `frontend/src/components/Nav.tsx` exposes `Jobs` to viewer and admin sessions, matching the existing read-only proxy permission for `/ingest/jobs`.

## Remaining S22 Work

S22 remains incomplete until the repository also records document/chunk inspection, retrieval-debug details, safe bulk reindex/delete workflows, accessibility/keyboard regression coverage, and broader Admin UX evidence.
