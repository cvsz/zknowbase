import sqlite3
import threading
from datetime import datetime, timezone

from app.queue_store import SQLiteIngestionQueue
from app.tenant_queue_store import ActiveIngestionJobError, TenantIngestionQueue


def tenant_queue(tmp_path) -> TenantIngestionQueue:
    db_path = tmp_path / "queue.db"
    return TenantIngestionQueue(
        SQLiteIngestionQueue(db_path),
        default_tenant_id="default",
        sqlite_path=str(db_path),
    )


def test_queue_tenant_binding_survives_retry(tmp_path):
    queue = tenant_queue(tmp_path)
    job = queue.enqueue(
        "doc-1",
        "url",
        "https://example.com",
        2,
        tenant_id="beta",
    )
    assert job.tenant_id == "beta"

    claimed = queue.claim_next("worker-1", 60)
    assert claimed is not None
    assert claimed.tenant_id == "beta"
    assert queue.fail(claimed.id, "worker-1", "transient") is True

    retried = queue.claim_next("worker-2", 60)
    assert retried is not None
    assert retried.id == job.id
    assert retried.tenant_id == "beta"


def test_queue_tenant_scope_hides_and_blocks_foreign_job(tmp_path):
    queue = tenant_queue(tmp_path)
    job = queue.enqueue(
        "doc-1",
        "url",
        "https://example.com",
        3,
        tenant_id="beta",
    )

    assert queue.get(job.id, "default") is None
    assert queue.list(100, "default") == []
    assert queue.cancel(job.id, "default") is False
    assert queue.get(job.id, "beta") is not None
    assert queue.cancel(job.id, "beta") is True


def test_legacy_queue_job_maps_deterministically_to_default_tenant(tmp_path):
    db_path = tmp_path / "queue.db"
    base = SQLiteIngestionQueue(db_path)
    legacy = base.enqueue("legacy-doc", "url", "https://example.com", 3)

    queue = TenantIngestionQueue(
        base,
        default_tenant_id="default",
        sqlite_path=str(db_path),
    )
    migrated = queue.get(legacy.id)
    assert migrated is not None
    assert migrated.tenant_id == "default"
    assert queue.get(legacy.id, "default") is not None


def test_tenant_binding_failure_cannot_leave_durable_unowned_job(tmp_path):
    queue = tenant_queue(tmp_path)
    assert queue.sqlite_path is not None
    with sqlite3.connect(queue.sqlite_path) as conn:
        conn.execute(
            """
            CREATE TRIGGER reject_job_tenant_bind
            BEFORE INSERT ON ingestion_job_tenants
            BEGIN
              SELECT RAISE(ABORT, 'tenant bind failed');
            END
            """
        )
        conn.commit()

    try:
        queue.enqueue("doc-bind-fail", "url", "https://example.com", tenant_id="beta")
    except sqlite3.DatabaseError:
        pass
    else:
        raise AssertionError("tenant binding failure must fail the enqueue")

    assert queue.base.list(100) == []


def test_enqueue_if_inactive_is_atomic_under_concurrency(tmp_path):
    queue = tenant_queue(tmp_path)
    barrier = threading.Barrier(2)
    successes = []
    conflicts = []
    result_lock = threading.Lock()

    def submit() -> None:
        barrier.wait(timeout=5)
        try:
            job = queue.enqueue_if_inactive(
                "doc-race",
                "url",
                "https://example.com/race",
                tenant_id="beta",
            )
        except ActiveIngestionJobError:
            with result_lock:
                conflicts.append(True)
        else:
            with result_lock:
                successes.append(job.id)

    threads = [threading.Thread(target=submit), threading.Thread(target=submit)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert len(successes) == 1
    assert len(conflicts) == 1
    jobs = queue.list(100, "beta")
    assert len(jobs) == 1
    assert jobs[0].id == successes[0]


def test_reindex_prior_state_is_tenant_scoped_and_durable(tmp_path):
    queue = tenant_queue(tmp_path)
    prior_updated_at = datetime.now(timezone.utc)
    job = queue.enqueue_if_inactive(
        "doc-reindex",
        "file",
        "/tmp/doc-reindex.md",
        tenant_id="beta",
        prior_status="ready",
        prior_error="old warning",
        prior_updated_at=prior_updated_at,
    )

    assert queue.reindex_prior_state(job.id, "default") is None
    state = queue.reindex_prior_state(job.id, "beta")
    assert state is not None
    assert state[0] == "ready"
    assert state[1] == "old warning"
    assert state[2] == prior_updated_at

    queue.clear_reindex_state(job.id)
    assert queue.reindex_prior_state(job.id, "beta") is None
