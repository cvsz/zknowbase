from app.queue_store import SQLiteIngestionQueue
from app.tenant_queue_store import TenantIngestionQueue


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
