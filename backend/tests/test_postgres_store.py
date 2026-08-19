import os
from datetime import timedelta
from uuid import uuid4

import pytest

from app.models.schemas import DocumentRecord
from app.postgres_store import (
    PostgresDocumentStore,
    PostgresSecurityStore,
    create_postgres_pool,
)
from app.queue_store import PostgresIngestionQueue

POSTGRES_URL = os.getenv("ZKB_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="local Postgres test DSN not configured")


def test_postgres_stores_share_pool():
    assert POSTGRES_URL is not None
    pool = create_postgres_pool(POSTGRES_URL, min_size=1, max_size=2)
    docs = PostgresDocumentStore(pool)
    security = PostgresSecurityStore(pool)
    queue = PostgresIngestionQueue(pool)
    assert docs.pool is security.pool is queue.pool
    pool.close()


def test_postgres_document_crud():
    assert POSTGRES_URL is not None
    pool = create_postgres_pool(POSTGRES_URL, min_size=1, max_size=2)
    store = PostgresDocumentStore(pool)
    doc_id = str(uuid4())
    now = store.now()
    record = DocumentRecord(
        id=doc_id,
        name="policy.md",
        source_type="file",
        source_uri="/data/policy.md",
        content_type="text/markdown",
        status="ready",
        chunk_count=4,
        size_bytes=1024,
        created_at=now,
        updated_at=now,
    )
    try:
        store.upsert(record)
        loaded = store.get(doc_id)
        assert loaded is not None
        assert loaded.name == "policy.md"
        assert loaded.chunk_count == 4
        assert any(item.id == doc_id for item in store.list())
        assert store.delete(doc_id) is True
        assert store.get(doc_id) is None
    finally:
        pool.close()


def test_postgres_key_rotation_and_audit():
    assert POSTGRES_URL is not None
    pool = create_postgres_pool(POSTGRES_URL, min_size=1, max_size=2)
    store = PostgresSecurityStore(pool)
    try:
        old, old_token = store.create_key(
            f"zworkforce-{uuid4().hex[:8]}",
            ["knowledge:read"],
            expires_at=store.now() + timedelta(days=30),
        )
        assert store.verify(old_token) is not None
        rotated = store.rotate(old.id)
        assert rotated is not None
        replacement, replacement_token = rotated
        assert replacement.rotated_from == old.id
        assert store.verify(old_token) is None
        assert store.verify(replacement_token) is not None
        event = store.audit(
            replacement.id,
            replacement.key_prefix,
            "integration.test",
            replacement.id,
            "success",
        )
        assert any(item.id == event.id for item in store.list_audit(100))
        assert store.revoke(replacement.id) is True
        assert store.verify(replacement_token) is None
    finally:
        pool.close()


def test_postgres_queue_claim_is_worker_owned():
    assert POSTGRES_URL is not None
    pool = create_postgres_pool(POSTGRES_URL, min_size=1, max_size=3)
    queue = PostgresIngestionQueue(pool)
    try:
        job = queue.enqueue(
            f"doc-{uuid4().hex[:8]}",
            "file",
            "/data/manual.md",
            max_attempts=2,
        )
        claimed = queue.claim_next("worker-a", lease_seconds=60)
        assert claimed is not None
        assert claimed.id == job.id
        assert claimed.worker_id == "worker-a"
        assert queue.renew(job.id, "worker-b", 60) is False
        assert queue.complete(job.id, "worker-b") is False
        assert queue.complete(job.id, "worker-a") is True
        assert queue.get(job.id).status == "completed"
    finally:
        pool.close()
