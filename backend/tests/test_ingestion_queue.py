from app.queue_store import SQLiteIngestionQueue


def test_sqlite_queue_claim_renew_complete(tmp_path):
    queue = SQLiteIngestionQueue(tmp_path / "queue.db")
    job = queue.enqueue("doc-1", "file", "/data/doc.md", max_attempts=3)

    claimed = queue.claim_next("worker-a", lease_seconds=60)
    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.status == "processing"
    assert claimed.attempts == 1
    assert claimed.worker_id == "worker-a"

    assert queue.renew(job.id, "worker-a", 60) is True
    assert queue.renew(job.id, "worker-b", 60) is False
    assert queue.complete(job.id, "worker-b") is False
    assert queue.complete(job.id, "worker-a") is True
    assert queue.get(job.id).status == "completed"


def test_sqlite_queue_retries_then_fails(tmp_path):
    queue = SQLiteIngestionQueue(tmp_path / "queue.db")
    job = queue.enqueue("doc-2", "url", "https://example.com/policy", max_attempts=2)

    first = queue.claim_next("worker-a", lease_seconds=60)
    assert first is not None
    assert queue.fail(first.id, "worker-a", "temporary") is True
    after_first = queue.get(job.id)
    assert after_first is not None
    assert after_first.status == "queued"
    assert after_first.attempts == 1

    second = queue.claim_next("worker-b", lease_seconds=60)
    assert second is not None
    assert second.attempts == 2
    assert queue.fail(second.id, "worker-b", "still failing") is True
    terminal = queue.get(job.id)
    assert terminal is not None
    assert terminal.status == "failed"
    assert terminal.error == "still failing"


def test_sqlite_queue_cancel_only_before_claim(tmp_path):
    queue = SQLiteIngestionQueue(tmp_path / "queue.db")
    queued = queue.enqueue("doc-3", "file", "/data/a.txt")
    assert queue.cancel(queued.id) is True
    assert queue.get(queued.id).status == "cancelled"

    processing = queue.enqueue("doc-4", "file", "/data/b.txt")
    assert queue.claim_next("worker-a", lease_seconds=60) is not None
    assert queue.cancel(processing.id) is False


def test_sqlite_queue_is_fifo(tmp_path):
    queue = SQLiteIngestionQueue(tmp_path / "queue.db")
    first = queue.enqueue("doc-a", "file", "/data/a.txt")
    second = queue.enqueue("doc-b", "file", "/data/b.txt")
    claimed = queue.claim_next("worker-a", lease_seconds=60)
    assert claimed is not None
    assert claimed.id == first.id
    assert claimed.id != second.id
