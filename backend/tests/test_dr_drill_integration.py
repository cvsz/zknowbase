import os
from pathlib import Path
from uuid import uuid4

import pytest

from app.backup import create_backup, restore_backup
from app.core.config import Settings
from app.models.schemas import DocumentRecord
from app.rag.vector_store import VectorStore
from app.store import DocumentStore

QDRANT_URL = os.getenv("ZKB_TEST_QDRANT_URL")
pytestmark = pytest.mark.skipif(not QDRANT_URL, reason="local Qdrant integration URL not configured")


@pytest.mark.asyncio
async def test_sqlite_upload_and_qdrant_disaster_recovery_drill(tmp_path: Path):
    assert QDRANT_URL is not None
    collection = f"zkb-dr-{uuid4().hex}"
    settings = Settings(
        api_key="this-is-a-test-secret-key",
        metadata_backend="sqlite",
        metadata_db=tmp_path / "data" / "zknowbase.db",
        upload_dir=tmp_path / "data" / "uploads",
        backup_dir=tmp_path / "data" / "backups",
        maintenance_lock_path=tmp_path / "data" / ".mutation.lock",
        qdrant_url=QDRANT_URL,
        qdrant_collection=collection,
    )
    settings.ensure_paths()

    tenant_id = "tenant-dr"
    document_id = str(uuid4())
    upload_path = settings.upload_dir / f"{document_id}.md"
    upload_path.write_text("authoritative recovery policy", encoding="utf-8")

    docs = DocumentStore(settings.metadata_db)
    now = docs.now()
    docs.upsert(
        DocumentRecord(
            id=document_id,
            tenant_id=tenant_id,
            name="recovery-policy.md",
            source_type="file",
            source_uri=str(upload_path),
            content_type="text/markdown",
            status="ready",
            chunk_count=1,
            size_bytes=upload_path.stat().st_size,
            created_at=now,
            updated_at=now,
        )
    )

    vectors = VectorStore(settings)
    try:
        await vectors.upsert_chunks(
            tenant_id,
            document_id,
            "recovery-policy.md",
            str(upload_path),
            ["authoritative recovery policy"],
            [[1.0, 0.0, 0.0]],
        )

        archive = await create_backup(settings)
        assert archive.is_file()
        assert archive.stat().st_mode & 0o077 == 0

        # Simulate destructive loss across every component owned by the native backup.
        docs.delete(document_id)
        upload_path.write_text("corrupted after backup", encoding="utf-8")
        await vectors.client.delete_collection(collection)
        assert docs.get(document_id) is None
        assert not await vectors.client.collection_exists(collection)

        safety = await restore_backup(settings, archive, yes=True, safety_backup=False)
        assert safety is None

        restored = DocumentStore(settings.metadata_db).get(document_id)
        assert restored is not None
        assert restored.tenant_id == tenant_id
        assert restored.name == "recovery-policy.md"
        assert upload_path.read_text(encoding="utf-8") == "authoritative recovery policy"

        recovered_vectors = await vectors.search(tenant_id, [1.0, 0.0, 0.0], 5)
        assert len(recovered_vectors) == 1
        assert recovered_vectors[0].tenant_id == tenant_id
        assert recovered_vectors[0].document_id == document_id
        assert recovered_vectors[0].text == "authoritative recovery policy"
    finally:
        if await vectors.client.collection_exists(collection):
            await vectors.client.delete_collection(collection)
        await vectors.client.close()
