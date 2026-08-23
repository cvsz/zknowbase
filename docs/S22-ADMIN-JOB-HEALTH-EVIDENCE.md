# S22 Admin Job Health Evidence

Date: 2026-08-23

This document records partial S22 evidence for tenant-safe ingestion job visibility in the Admin UI. It does not claim full S22 completion.

## Scope

The Admin UI exposes a `Jobs` view that reads ingestion jobs through the existing same-origin Admin proxy and backend tenant-scoped `/api/v1/ingest/jobs` endpoint. The browser still never receives the backend service key; authorization remains enforced by the server-side proxy and service-key scopes.

## Operator Visibility

The page shows a clearly labeled recent sample of up to 100 jobs for the authenticated tenant, with status counts, retry-eligible queued jobs, attempts, lease expiry, worker identity, source type/URI, updated time, document ID, job ID, and bounded failure details. The cards are explicitly not presented as lifetime totals.

Tenant scoping is applied before the list limit in both SQLite and Postgres. This prevents another tenant's newer jobs from consuming the global limit and producing a false empty result for the authenticated tenant. Legacy unmapped jobs retain the documented deterministic default-tenant fallback. Tenant-scoped active-job lookup also uses a direct database predicate rather than a bounded global sample.

## Evidence

- `frontend/src/lib/api.ts` fetches jobs through `/api/zkb/ingest/jobs?limit=...`.
- `frontend/src/app/jobs/page.tsx` renders the recent tenant-scoped sample, labels the bounded sampling semantics, and counts retries only for queued jobs with prior attempts.
- `frontend/tests/admin-jobs-api.test.ts` verifies the Admin client uses the same-origin proxy path for job reads and uses an explicit `.ts` import compatible with the native Node test runner.
- `backend/app/tenant_queue_store.py` selects tenant-owned rows before applying the bounded result limit for both SQLite and Postgres.
- `backend/tests/test_tenant_queue_listing.py` covers filter-before-limit behavior, deterministic legacy default-tenant visibility, tenant-scoped active lookup, and Postgres parity when the CI Postgres service is available.
- `frontend/src/components/Nav.tsx` exposes `Jobs` to viewer and admin sessions, matching the existing read-only proxy permission for `/ingest/jobs`.

## Security and Compatibility

No browser-side service credential is introduced. The backend remains the tenant authority, foreign tenant jobs are not returned by tenant-scoped listing/active lookup, SQLite remains the default metadata/queue backend, and Postgres remains the optional self-hosted HA path. No Redis, Celery, hosted identity, or paid service is introduced.

## Remaining S22 Work

S22 remains incomplete until the repository also records document/chunk inspection, retrieval-debug details, safe bulk reindex/delete workflows, accessibility/keyboard regression coverage, and broader Admin UX evidence.
