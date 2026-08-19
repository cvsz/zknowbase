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
    job = SimpleNamespace(id="job-1", document_id="doc-1")
    settings = SimpleNamespace(worker_lease_seconds=30)

    await worker._run_job(queue, job, "worker-a", settings)
    assert queue.completed == [("job-1", "worker-a")]
