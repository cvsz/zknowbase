from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.models.schemas import DocumentRecord
from app.rag.vector_store import VectorStore
from app.store import DocumentStore


def _record(doc_id: str, tenant_id: str) -> DocumentRecord:
    now = datetime.now(timezone.utc)
    return DocumentRecord(
        id=doc_id,
        name=f"{tenant_id}.md",
        tenant_id=tenant_id,
        source_type="file",
        status="ready",
        created_at=now,
        updated_at=now,
    )


def test_sqlite_document_tenant_is_persisted_and_legacy_defaults(tmp_path):
    db_path = tmp_path / "metadata.db"
    store = DocumentStore(db_path)
    store.upsert(_record("tenant-doc", "acme"))

    loaded = DocumentStore(db_path).get("tenant-doc")
    assert loaded is not None
    assert loaded.tenant_id == "acme"


def test_document_tenant_validation_rejects_invalid_identifier():
    with pytest.raises(ValueError):
        _record("bad", "../other-tenant")


@pytest.mark.asyncio
async def test_qdrant_search_always_includes_tenant_filter():
    settings = Settings(api_key="this-is-a-test-secret-key")
    store = VectorStore(settings)

    class FakeClient:
        def __init__(self):
            self.query_filter = None

        async def collection_exists(self, _name):
            return True

        async def query_points(self, **kwargs):
            self.query_filter = kwargs["query_filter"]
            return SimpleNamespace(
                points=[
                    SimpleNamespace(
                        id="point-1",
                        score=0.9,
                        payload={
                            "tenant_id": "acme",
                            "document_id": "doc-1",
                            "document_name": "policy.md",
                            "chunk_id": "chunk-1",
                            "chunk_index": 0,
                            "text": "policy",
                        },
                    ),
                    SimpleNamespace(
                        id="point-2",
                        score=0.8,
                        payload={
                            "tenant_id": "other",
                            "document_id": "doc-2",
                            "document_name": "private.md",
                            "chunk_id": "chunk-2",
                            "chunk_index": 0,
                            "text": "must not escape",
                        },
                    ),
                ]
            )

    fake = FakeClient()
    store.client = fake
    results = await store.search("acme", [0.1, 0.2], 5)

    assert fake.query_filter is not None
    conditions = {condition.key: condition.match.value for condition in fake.query_filter.must}
    assert conditions["tenant_id"] == "acme"
    assert [result.document_id for result in results] == ["doc-1"]
    assert results[0].tenant_id == "acme"


@pytest.mark.asyncio
async def test_qdrant_delete_requires_tenant_and_document_conditions():
    settings = Settings(api_key="this-is-a-test-secret-key")
    store = VectorStore(settings)

    class FakeClient:
        def __init__(self):
            self.selector = None

        async def collection_exists(self, _name):
            return True

        async def delete(self, **kwargs):
            self.selector = kwargs["points_selector"]

    fake = FakeClient()
    store.client = fake
    await store.delete_document("acme", "doc-1")

    conditions = {
        condition.key: condition.match.value
        for condition in fake.selector.filter.must
    }
    assert conditions == {"tenant_id": "acme", "document_id": "doc-1"}

    with pytest.raises(ValueError):
        await store.delete_document("", "doc-1")
