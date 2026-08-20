from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

import app.worker as worker


class FakeQueue:
    def __init__(self):
        self.completed = []

    def renew(self, job_id, worker_id, lease_seconds):
        return True

    def complete(self, job_id, worker_id):
        self.completed.append((job_id, worker_id))
        return True

    def fail(self, job_id, worker_id, error):
        raise AssertionError("successful job must not fail")


@pytest.mark.asyncio
async def test_run_job_finishes_before_heartbeat(monkeypatch):
    async def fake_process(job, settings):
        return SimpleNamespace(id=job.document_id, chunk_count=2)

    monkeypatch.setattr(worker, "process_ingestion_job", fake_process)
    queue = FakeQueue()
    job = SimpleNamespace(id="job-1", document_id="doc-1", tenant_id="default")
    settings = SimpleNamespace(worker_lease_seconds=30)

    await worker._run_job(queue, job, "worker-a", settings)
    assert queue.completed == [("job-1", "worker-a")]


@pytest.mark.asyncio
async def test_stale_worker_does_not_mutate_document_after_lease_loss(monkeypatch):
    async def failing_process(job, settings):
        raise RuntimeError("provider failure")

    class StaleQueue:
        def renew(self, job_id, worker_id, lease_seconds):
            return True

        def complete(self, job_id, worker_id):
            return False

        def fail(self, job_id, worker_id, error):
            return False

    def forbidden_document_store(settings):
        raise AssertionError("stale worker must not reconcile document state")

    monkeypatch.setattr(worker, "process_ingestion_job", failing_process)
    monkeypatch.setattr(worker, "document_store", forbidden_document_store)
    job = SimpleNamespace(id="job-stale", document_id="doc-stale", tenant_id="default")
    settings = SimpleNamespace(worker_lease_seconds=30)

    await worker._run_job(StaleQueue(), job, "worker-old", settings)


@pytest.mark.asyncio
async def test_worker_drain_finishes_claimed_job_without_claiming_another(monkeypatch, tmp_path):
    stop_event = __import__("asyncio").Event()
    first = SimpleNamespace(
        id="job-1",
        document_id="doc-1",
        tenant_id="default",
        attempts=1,
        max_attempts=3,
    )
    second = SimpleNamespace(
        id="job-2",
        document_id="doc-2",
        tenant_id="default",
        attempts=1,
        max_attempts=3,
    )

    class DrainQueue:
        def __init__(self):
            self.claim_calls = 0

        def claim_next(self, worker_id, lease_seconds):
            self.claim_calls += 1
            return first if self.claim_calls == 1 else second

    queue = DrainQueue()
    settings = SimpleNamespace(
        metadata_backend="sqlite",
        maintenance_lock_path=tmp_path / ".maintenance.lock",
        worker_lease_seconds=30,
        worker_poll_seconds=60.0,
    )
    drained = []

    async def fake_run_job(_queue, job, worker_id, _settings):
        drained.append(job.id)
        stop_event.set()

    @asynccontextmanager
    async def unlocked(*args, **kwargs):
        yield

    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "configure_tracing", lambda _settings: None)
    monkeypatch.setattr(worker, "ingestion_queue", lambda _settings: queue)
    monkeypatch.setattr(worker, "async_mutation_lock", unlocked)
    monkeypatch.setattr(worker, "_reap_and_reconcile", lambda _queue, _settings: None)
    monkeypatch.setattr(worker, "_run_job", fake_run_job)

    await worker.run_worker(stop_event)

    assert drained == ["job-1"]
    assert queue.claim_calls == 1


@pytest.mark.asyncio
async def test_worker_with_pre_requested_stop_never_claims(monkeypatch, tmp_path):
    stop_event = __import__("asyncio").Event()
    stop_event.set()

    class NoClaimQueue:
        def claim_next(self, worker_id, lease_seconds):
            raise AssertionError("draining worker must not claim new work")

    settings = SimpleNamespace(
        metadata_backend="sqlite",
        maintenance_lock_path=tmp_path / ".maintenance.lock",
        worker_lease_seconds=30,
        worker_poll_seconds=60.0,
    )
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "configure_tracing", lambda _settings: None)
    monkeypatch.setattr(worker, "ingestion_queue", lambda _settings: NoClaimQueue())

    await worker.run_worker(stop_event)
