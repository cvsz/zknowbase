import os
from uuid import uuid4

import pytest

from app.postgres_store import create_postgres_pool
from app.queue_store import PostgresIngestionQueue, SQLiteIngestionQueue
from app.tenant_queue_store import TenantIngestionQueue

POSTGRES_URL = os.getenv("ZKB_TEST_POSTGRES_URL")


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


@pytest.mark.skipif(not POSTGRES_URL, reason="local Postgres test DSN not configured")
def test_postgres_tenant_list_filters_before_limit():
    assert POSTGRES_URL is not None
    pool = create_postgres_pool(POSTGRES_URL, min_size=1, max_size=2)
    base = PostgresIngestionQueue(pool)
    queue = TenantIngestionQueue(
        base,
        default_tenant_id="default",
        postgres_pool=pool,
    )
    prefix = uuid4().hex[:10]
    created_ids: list[str] = []
    try:
        target = queue.enqueue(
            f"{prefix}-target",
            "file",
            f"/data/{prefix}-target.txt",
            tenant_id=f"{prefix}-tenant-a",
        )
        created_ids.append(target.id)
        for index in range(3):
            job = queue.enqueue(
                f"{prefix}-foreign-{index}",
                "file",
                f"/data/{prefix}-foreign-{index}.txt",
                tenant_id=f"{prefix}-tenant-b",
            )
            created_ids.append(job.id)

        jobs = queue.list(2, tenant_id=f"{prefix}-tenant-a")

        assert [job.id for job in jobs] == [target.id]
        assert jobs[0].tenant_id == f"{prefix}-tenant-a"
        assert queue.active_for_document(
            f"{prefix}-target", tenant_id=f"{prefix}-tenant-a"
        ) is True
        assert queue.active_for_document(
            f"{prefix}-target", tenant_id=f"{prefix}-tenant-b"
        ) is False
    finally:
        with pool.connection() as conn:
            conn.execute("DELETE FROM ingestion_job_tenants WHERE job_id = ANY(%s)", (created_ids,))
            conn.execute("DELETE FROM ingestion_jobs WHERE id = ANY(%s)", (created_ids,))
        pool.close()
