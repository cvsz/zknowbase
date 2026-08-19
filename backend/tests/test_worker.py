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
