from app.queue_store import SQLiteIngestionQueue
from app.tenant_queue_store import TenantIngestionQueue


def _queue(tmp_path) -> TenantIngestionQueue:
    db_path = tmp_path / "queue.db"
    return TenantIngestionQueue(
        SQLiteIngestionQueue(db_path),
        default_tenant_id="default",
        sqlite_path=str(db_path),
    )


def test_tenant_list_filters_before_limit(tmp_path):
    queue = _queue(tmp_path)

    target = queue.enqueue(
        "target-doc",
        "file",
        "/data/target.txt",
        tenant_id="tenant-a",
    )
    for index in range(3):
        queue.enqueue(
            f"foreign-{index}",
            "file",
            f"/data/foreign-{index}.txt",
            tenant_id="tenant-b",
        )

    jobs = queue.list(2, tenant_id="tenant-a")

    assert [job.id for job in jobs] == [target.id]
    assert jobs[0].tenant_id == "tenant-a"


def test_default_tenant_list_includes_unmapped_legacy_rows_before_limit(tmp_path):
    db_path = tmp_path / "queue.db"
    base = SQLiteIngestionQueue(db_path)
    legacy = base.enqueue("legacy-doc", "file", "/data/legacy.txt")
    queue = TenantIngestionQueue(
        base,
        default_tenant_id="default",
        sqlite_path=str(db_path),
    )
    for index in range(3):
        queue.enqueue(
            f"foreign-{index}",
            "file",
            f"/data/foreign-{index}.txt",
            tenant_id="tenant-b",
        )

    jobs = queue.list(2, tenant_id="default")

    assert [job.id for job in jobs] == [legacy.id]
    assert jobs[0].tenant_id == "default"


def test_tenant_active_lookup_is_scoped_without_sampling(tmp_path):
    queue = _queue(tmp_path)
    queue.enqueue("shared-doc", "file", "/data/a.txt", tenant_id="tenant-a")

    assert queue.active_for_document("shared-doc", tenant_id="tenant-a") is True
    assert queue.active_for_document("shared-doc", tenant_id="tenant-b") is False
