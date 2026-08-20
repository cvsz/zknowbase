# Worker Resilience and Graceful Drain

The zknowbase ingestion worker uses the durable metadata-database queue and does not require Redis, Celery, or an external broker.

## Graceful shutdown contract

The worker installs local process handlers for `SIGTERM` and `SIGINT` where the runtime supports asyncio signal handlers. A shutdown request sets an in-process drain event; it does not cancel the currently claimed ingestion job.

The drain contract is:

1. stop claiming new jobs as soon as the drain event is observable;
2. if a job already owns a valid lease, keep its heartbeat active while that job finishes;
3. transition the active job through the normal complete/fail/requeue path before worker exit;
4. do not begin a second claim after shutdown was requested;
5. log `worker_shutdown_requested` and `worker_stopped` without document contents or credentials.

A signal arriving while the worker waits for its maintenance lock is checked before the next queue claim. Idle polling waits on the same drain event, so shutdown does not need to wait for the full polling interval.

## Container orchestration

Production orchestrators should send `SIGTERM` first and allow a termination grace period longer than the normal maximum duration expected for one ingestion attempt plus queue/lease bookkeeping. If the orchestrator sends `SIGKILL` before that interval, graceful drain cannot run; the durable lease-reaping path remains the crash-recovery mechanism and will requeue or terminally fail an expired job according to its retry budget.

The graceful-drain path does not alter tenant ownership, retry limits, cancellation semantics, or lease authority. A stale worker still cannot complete or reconcile a job after losing queue ownership.

## Evidence

Backend regression tests prove that:

- a drain request raised while a job is active allows that claimed job to finish but prevents a second claim;
- a worker started with an already-requested stop never claims work;
- existing stale-worker tests continue to reject state reconciliation after lease ownership is lost.

Further S23 evidence remains required for multi-worker load, controlled Postgres/Qdrant/Ollama outage recovery, bounded resource growth during dependency outages, and calibrated deployment/SLO envelopes.
