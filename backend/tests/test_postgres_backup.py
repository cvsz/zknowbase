import os
from pathlib import Path
from uuid import uuid4

import pytest

from app.backup import _backup_postgres, _restore_postgres
from app.core.config import Settings
from app.models.schemas import DocumentRecord
from app.store_factory import document_store, ingestion_queue, security_store

POSTGRES_URL = os.getenv("ZKB_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="local Postgres test DSN not configured")


def test_postgres_metadata_backup_restore_round_trip(tmp_path: Path):
    assert POSTGRES_URL is not None
    settings = Settings(
        api_key="this-is-a-test-secret-key",
        metadata_backend="postgres",
        postgres_url=POSTGRES_URL,
        postgres_pool_min_size=1,
        postgres_pool_max_size=2,
        upload_dir=tmp_path / "uploads",
        backup_dir=tmp_path / "backups",
        maintenance_lock_path=tmp_path / ".lock",
    )
    settings.ensure_paths()
    docs = document_store(settings)
    keys = security_store(settings)
    queue = ingestion_queue(settings)
    doc_id = f"backup-doc-{uuid4().hex}"
    now = docs.now()
    docs.upsert(
        DocumentRecord(
            id=doc_id,
            name="backup.md",
            source_type="file",
            source_uri="/data/uploads/backup.md",
            content_type="text/markdown",
            status="ready",
            chunk_count=1,
            size_bytes=10,
            created_at=now,
            updated_at=now,
        )
    )
    key, token = keys.create_key(f"backup-key-{uuid4().hex}", ["knowledge:read"])
    job = queue.enqueue(doc_id, "file", "/data/uploads/backup.md")

    dump = tmp_path / "metadata.postgres.json"
    _backup_postgres(settings, dump)
    assert dump.is_file()

    docs.delete(doc_id)
    keys.revoke(key.id)
    queue.cancel(job.id)
    assert docs.get(doc_id) is None

    _restore_postgres(settings, dump)
    assert document_store(settings).get(doc_id) is not None
    restored_key = security_store(settings).get_key(key.id)
    assert restored_key is not None
    assert restored_key.revoked_at is None
    assert security_store(settings).verify(token) is not None
    restored_job = ingestion_queue(settings).get(job.id)
    assert restored_job is not None
    assert restored_job.status == "queued"
