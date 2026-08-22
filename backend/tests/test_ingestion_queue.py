from concurrent.futures import ThreadPoolExecutor

from app.queue_store import SQLiteIngestionQueue


def test_sqlite_queue_claim_renew_complete(tmp_path):
    queue = SQLiteIngestionQueue(tmp_path / "queue.db")
    job = queue.enqueue("doc-1", "file", "/data/doc.md", max_attempts=3)

    assert queue.active_for_document("doc-1") is True
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
    assert queue.active_for_document("doc-1") is False


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


def test_sqlite_queue_reaps_terminal_expired_lease(tmp_path):
    queue = SQLiteIngestionQueue(tmp_path / "queue.db")
    job = queue.enqueue("doc-expired", "file", "/data/expired.txt", max_attempts=1)
    claimed = queue.claim_next("worker-a", lease_seconds=60)
    assert claimed is not None

    with queue._connect() as conn:
        conn.execute(
            "UPDATE ingestion_jobs SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",
            (job.id,),
        )
        conn.commit()

    changed = queue.reap_expired()
    assert len(changed) == 1
    assert changed[0].id == job.id
    assert changed[0].status == "failed"
    assert changed[0].error == "job lease expired"
    assert queue.active_for_document("doc-expired") is False


def test_sqlite_queue_rejects_worker_mutation_after_lease_expiry(tmp_path):
    queue = SQLiteIngestionQueue(tmp_path / "queue.db")
    job = queue.enqueue("doc-stale", "file", "/data/stale.txt", max_attempts=2)
    claimed = queue.claim_next("worker-a", lease_seconds=60)
    assert claimed is not None

    with queue._connect() as conn:
        conn.execute(
            "UPDATE ingestion_jobs SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",
            (job.id,),
        )
        conn.commit()

    assert queue.renew(job.id, "worker-a", 60) is False
    assert queue.complete(job.id, "worker-a") is False
    assert queue.fail(job.id, "worker-a", "stale failure") is False

    changed = queue.reap_expired()
    assert len(changed) == 1
    assert changed[0].id == job.id
    assert changed[0].status == "queued"
    assert changed[0].worker_id is None


def test_sqlite_queue_concurrent_workers_claim_each_job_once(tmp_path):
    db_path = tmp_path / "queue.db"
    queue = SQLiteIngestionQueue(db_path)
    jobs = [
        queue.enqueue(f"doc-concurrent-{index}", "file", f"/data/{index}.txt")
        for index in range(20)
    ]

    def claim_all(worker_index: int) -> list[str]:
        worker_queue = SQLiteIngestionQueue(db_path)
        claimed_ids: list[str] = []
        while claimed := worker_queue.claim_next(f"worker-{worker_index}", lease_seconds=60):
            claimed_ids.append(claimed.id)
        return claimed_ids

    with ThreadPoolExecutor(max_workers=4) as pool:
        claimed = [
            job_id
            for worker_claims in pool.map(claim_all, range(4))
            for job_id in worker_claims
        ]

    assert sorted(claimed) == sorted(job.id for job in jobs)
    assert len(set(claimed)) == len(jobs)
