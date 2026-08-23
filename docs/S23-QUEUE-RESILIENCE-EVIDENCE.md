# S23 Queue Resilience Evidence

Date: 2026-08-20

This document records partial S23 evidence for ingestion-queue lease authority and local multi-worker claim behavior. It does not claim full S23 completion.

## Scope

This slice hardens the durable ingestion queue so a worker can mutate a processing job only while it still owns an unexpired lease. The same guard is applied to SQLite and Postgres queue backends for lease renewal, completion, and failure/requeue transitions.

## Evidence

- `backend/tests/test_ingestion_queue.py::test_sqlite_queue_rejects_worker_mutation_after_lease_expiry` proves an expired worker lease cannot be renewed, completed, or failed by the stale worker and remains recoverable through the lease reaper.
- `backend/tests/test_ingestion_queue.py::test_sqlite_queue_concurrent_workers_claim_each_job_once` uses four independent SQLite queue instances against the same database file and proves twenty queued jobs are claimed exactly once.
- Existing worker ownership tests continue to prove stale workers do not reconcile document state after queue ownership is lost.

## Remaining S23 Work

S23 remains incomplete until the repository also records Postgres multi-worker/load evidence, controlled Qdrant/Postgres/Ollama outage recovery tests, bounded resource-growth evidence during dependency outages, graceful shutdown/drain evidence for release scope, and calibrated deployment/SLO capacity assumptions.
