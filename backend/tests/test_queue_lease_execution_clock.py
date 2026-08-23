import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.postgres_store import create_postgres_pool
from app.queue_store import PostgresIngestionQueue, SQLiteIngestionQueue

POSTGRES_URL = os.getenv("ZKB_TEST_POSTGRES_URL")


def _invoke_worker_mutation(queue, operation: str, job_id: str) -> bool:
    if operation == "renew":
        return queue.renew(job_id, "worker-a", 60)
    if operation == "complete":
        return queue.complete(job_id, "worker-a")
    if operation == "fail":
        return queue.fail(job_id, "worker-a", "stale worker failure")
    raise AssertionError(f"unsupported operation: {operation}")


@pytest.mark.parametrize("operation", ["renew", "complete", "fail"])
def test_sqlite_worker_mutations_use_database_clock(tmp_path, monkeypatch, operation):
    queue = SQLiteIngestionQueue(tmp_path / f"queue-{operation}.db")
    job = queue.enqueue(f"doc-{operation}", "file", f"/data/{operation}.txt", max_attempts=2)
    claimed = queue.claim_next("worker-a", lease_seconds=60)
    assert claimed is not None

    expired = datetime.now(timezone.utc) - timedelta(seconds=1)
    with queue._connect() as conn:
        conn.execute(
            "UPDATE ingestion_jobs SET lease_expires_at=? WHERE id=?",
            (expired.isoformat(), job.id),
        )
        conn.commit()

    # Simulate an application timestamp sampled before a connection/lock wait.
    # A stale Python clock would authorize the mutation in the old implementation;
    # the database execution-time clock must reject it.
    stale_application_time = expired - timedelta(minutes=5)
    monkeypatch.setattr(queue, "now", lambda: stale_application_time)

    assert _invoke_worker_mutation(queue, operation, job.id) is False
    loaded = queue.get(job.id)
    assert loaded is not None
    assert loaded.status == "processing"
    assert loaded.worker_id == "worker-a"


@pytest.mark.skipif(not POSTGRES_URL, reason="local Postgres test DSN not configured")
@pytest.mark.parametrize("operation", ["renew", "complete", "fail"])
def test_postgres_worker_mutations_use_database_clock(monkeypatch, operation):
    assert POSTGRES_URL is not None
    pool = create_postgres_pool(POSTGRES_URL, min_size=1, max_size=2)
    queue = PostgresIngestionQueue(pool)
    job_id = ""
    try:
        job = queue.enqueue(
            f"doc-lease-clock-{uuid4().hex[:8]}",
            "file",
            "/data/lease-clock.txt",
            max_attempts=2,
        )
        job_id = job.id
        claimed = queue.claim_next("worker-a", lease_seconds=60)
        assert claimed is not None
        assert claimed.id == job.id

        expired = datetime.now(timezone.utc) - timedelta(seconds=1)
        with pool.connection() as conn:
            conn.execute(
                "UPDATE ingestion_jobs SET lease_expires_at=%s WHERE id=%s",
                (expired, job.id),
            )

        # Postgres must evaluate authority with clock_timestamp() at statement
        # execution, not a Python timestamp captured before DB contention.
        stale_application_time = expired - timedelta(minutes=5)
        monkeypatch.setattr(queue, "now", lambda: stale_application_time)

        assert _invoke_worker_mutation(queue, operation, job.id) is False
        loaded = queue.get(job.id)
        assert loaded is not None
        assert loaded.status == "processing"
        assert loaded.worker_id == "worker-a"
    finally:
        if job_id:
            with pool.connection() as conn:
                conn.execute("DELETE FROM ingestion_jobs WHERE id=%s", (job_id,))
        pool.close()
