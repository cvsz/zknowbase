import os
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.rag.vector_store import VectorStore

QDRANT_URL = os.getenv("ZKB_TEST_QDRANT_URL")
pytestmark = pytest.mark.skipif(not QDRANT_URL, reason="local Qdrant integration URL not configured")


@pytest.mark.asyncio
async def test_real_qdrant_lifecycle_enforces_tenant_partition(tmp_path):
    assert QDRANT_URL is not None
    collection = f"zkb-ci-{uuid4().hex}"
    settings = Settings(
        api_key="this-is-a-test-secret-key",
        qdrant_url=QDRANT_URL,
        qdrant_collection=collection,
        metadata_db=tmp_path / "metadata.db",
        upload_dir=tmp_path / "uploads",
    )
    store = VectorStore(settings)
    try:
        await store.upsert_chunks(
            "tenant-a",
            "shared-document-id",
            "tenant-a.md",
            None,
            ["alpha policy"],
            [[1.0, 0.0, 0.0]],
        )
        await store.upsert_chunks(
            "tenant-b",
            "shared-document-id",
            "tenant-b.md",
            None,
            ["beta policy"],
            [[0.0, 1.0, 0.0]],
        )

        tenant_a = await store.search("tenant-a", [1.0, 0.0, 0.0], 10)
        tenant_b = await store.search("tenant-b", [0.0, 1.0, 0.0], 10)

        assert [item.tenant_id for item in tenant_a] == ["tenant-a"]
        assert [item.document_name for item in tenant_a] == ["tenant-a.md"]
        assert [item.tenant_id for item in tenant_b] == ["tenant-b"]
        assert [item.document_name for item in tenant_b] == ["tenant-b.md"]

        await store.delete_document("tenant-a", "shared-document-id")

        assert await store.search("tenant-a", [1.0, 0.0, 0.0], 10) == []
        remaining = await store.search("tenant-b", [0.0, 1.0, 0.0], 10)
        assert len(remaining) == 1
        assert remaining[0].tenant_id == "tenant-b"
        assert remaining[0].document_name == "tenant-b.md"
    finally:
        if await store.client.collection_exists(collection):
            await store.client.delete_collection(collection)
        await store.client.close()


@pytest.mark.asyncio
async def test_real_qdrant_operations_fail_closed_without_tenant(tmp_path):
    assert QDRANT_URL is not None
    settings = Settings(
        api_key="this-is-a-test-secret-key",
        qdrant_url=QDRANT_URL,
        qdrant_collection=f"zkb-ci-{uuid4().hex}",
        metadata_db=tmp_path / "metadata.db",
        upload_dir=tmp_path / "uploads",
    )
    store = VectorStore(settings)
    try:
        with pytest.raises(ValueError, match="tenant_id is required"):
            await store.search("", [1.0, 0.0], 5)
        with pytest.raises(ValueError, match="tenant_id is required"):
            await store.delete_document("", "doc-1")
        with pytest.raises(ValueError, match="tenant_id is required"):
            await store.upsert_chunks("", "doc-1", "doc.md", None, ["text"], [[1.0, 0.0]])
    finally:
        await store.client.close()
