import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app
from app.rag.providers import AIProviders
from app.rag.vector_store import VectorStore
from app.store_factory import security_store

QDRANT_URL = os.getenv("ZKB_TEST_QDRANT_URL")
pytestmark = pytest.mark.skipif(not QDRANT_URL, reason="local Qdrant test URL not configured")


def _settings(tmp_path) -> Settings:
    assert QDRANT_URL is not None
    settings = Settings(
        api_key="ci-e2e-bootstrap-key-0123456789",
        default_tenant_id="tenant-a",
        metadata_backend="sqlite",
        metadata_db=tmp_path / "e2e.db",
        upload_dir=tmp_path / "uploads",
        backup_dir=tmp_path / "backups",
        maintenance_lock_path=tmp_path / ".mutation.lock",
        qdrant_url=QDRANT_URL,
        qdrant_collection=f"zkb-e2e-{uuid4().hex}",
        retrieval_mode="dense",
        embedding_provider="ollama",
        llm_provider="ollama",
        malware_scan_mode="validate",
    )
    settings.ensure_paths()
    return settings


@pytest.mark.asyncio
async def test_service_api_ingest_retrieve_query_delete_and_tenant_isolation(monkeypatch, tmp_path):
    settings = _settings(tmp_path)

    async def fake_local_ollama(self, url, payload, headers=None):
        del self, headers
        if url.endswith("/api/embed"):
            texts = payload["input"]
            return {"embeddings": [[1.0, 0.0, 0.0, 0.0] for _ in texts]}
        if url.endswith("/api/chat"):
            prompt = payload["messages"][-1]["content"]
            assert "annual leave requires manager approval" in prompt
            return {"message": {"content": "Annual leave requires manager approval [S1]."}}
        raise AssertionError(f"unexpected provider endpoint: {url}")

    monkeypatch.setattr(AIProviders, "_post_json", fake_local_ollama)
    app.dependency_overrides[get_settings] = lambda: settings

    tenant_b_key, tenant_b_secret = security_store(settings).create_key(
        "tenant-b-reader",
        ["knowledge:read"],
        tenant_id="tenant-b",
    )
    assert tenant_b_key.tenant_id == "tenant-b"

    try:
        with TestClient(app) as client:
            headers_a = {"X-API-Key": settings.api_key, "X-Request-ID": "e2e-ingest-1"}
            ingest = client.post(
                "/api/v1/ingest",
                headers=headers_a,
                files={
                    "file": (
                        "leave-policy.txt",
                        b"Annual leave requires manager approval before booking travel.",
                        "text/plain",
                    )
                },
            )
            assert ingest.status_code == 200, ingest.text
            document = ingest.json()["document"]
            assert document["status"] == "ready"
            assert document["tenant_id"] == "tenant-a"
            assert document["chunk_count"] >= 1
            document_id = document["id"]

            listed = client.get("/api/v1/documents", headers=headers_a)
            assert listed.status_code == 200
            assert [item["id"] for item in listed.json()] == [document_id]

            search = client.post(
                "/api/v1/search",
                headers={**headers_a, "X-Request-ID": "e2e-search-1"},
                json={"query": "annual leave approval", "top_k": 3},
            )
            assert search.status_code == 200, search.text
            results = search.json()["results"]
            assert results
            assert results[0]["document_id"] == document_id
            assert results[0]["tenant_id"] == "tenant-a"
            assert "manager approval" in results[0]["text"].lower()

            query = client.post(
                "/api/v1/query",
                headers={**headers_a, "X-Request-ID": "e2e-query-1"},
                json={"question": "What approval is needed for annual leave?", "top_k": 3},
            )
            assert query.status_code == 200, query.text
            payload = query.json()
            assert payload["answer"] == "Annual leave requires manager approval [S1]."
            assert payload["sources"][0]["document_id"] == document_id
            assert payload["sources"][0]["tenant_id"] == "tenant-a"

            headers_b = {"X-API-Key": tenant_b_secret, "X-Request-ID": "e2e-tenant-b"}
            isolated_list = client.get("/api/v1/documents", headers=headers_b)
            assert isolated_list.status_code == 200
            assert isolated_list.json() == []

            isolated_search = client.post(
                "/api/v1/search",
                headers=headers_b,
                json={"query": "annual leave approval", "top_k": 3},
            )
            assert isolated_search.status_code == 200
            assert isolated_search.json()["results"] == []

            denied_delete = client.delete(f"/api/v1/documents/{document_id}", headers=headers_b)
            assert denied_delete.status_code == 403

            deleted = client.delete(f"/api/v1/documents/{document_id}", headers=headers_a)
            assert deleted.status_code == 204

            after_delete = client.post(
                "/api/v1/search",
                headers=headers_a,
                json={"query": "annual leave approval", "top_k": 3},
            )
            assert after_delete.status_code == 200
            assert after_delete.json()["results"] == []
    finally:
        app.dependency_overrides.pop(get_settings, None)
        vector_store = VectorStore(settings)
        if await vector_store.client.collection_exists(settings.qdrant_collection):
            await vector_store.client.delete_collection(settings.qdrant_collection)
        await vector_store.client.close()
