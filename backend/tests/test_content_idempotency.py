from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.routes as routes
from app.api.routes import router as core_router
from app.content_identity import file_document_id, sha256_content
from app.core.config import get_settings


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("ZKB_API_KEY", "this-is-a-test-secret-key")
    monkeypatch.setenv("ZKB_METADATA_BACKEND", "sqlite")
    monkeypatch.setenv("ZKB_METADATA_DB", str(tmp_path / "zknowbase.db"))
    monkeypatch.setenv("ZKB_UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    settings = get_settings()
    settings.ensure_paths()

    async def fake_index(record, text, _settings):
        record.status = "ready"
        record.chunk_count = 1
        record.updated_at = routes.utcnow()
        return routes.document_store(_settings).upsert(record)

    monkeypatch.setattr(routes, "index_document", fake_index)
    app = FastAPI()
    app.include_router(core_router, prefix="/api/v1")
    return TestClient(app)


def test_file_document_id_is_stable_and_tenant_scoped():
    digest = sha256_content(b"same bytes")
    assert file_document_id("alpha", digest) == file_document_id("alpha", digest)
    assert file_document_id("alpha", digest) != file_document_id("beta", digest)


def test_file_document_id_rejects_invalid_hash():
    try:
        file_document_id("alpha", "not-a-sha256")
    except ValueError as exc:
        assert "SHA-256" in str(exc)
    else:
        raise AssertionError("invalid content hash must fail closed")


def test_sync_file_ingestion_returns_existing_document_for_duplicate_bytes(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"X-API-Key": "this-is-a-test-secret-key"}
    content = b"# Idempotent upload\nThe same bytes should retain one document identity."

    first = client.post(
        "/api/v1/ingest",
        headers=headers,
        files={"file": ("first.md", content, "text/markdown")},
    )
    second = client.post(
        "/api/v1/ingest",
        headers=headers,
        files={"file": ("renamed.md", content, "text/markdown")},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["document"]["id"] == first.json()["document"]["id"]
    assert second.json()["document"]["name"] == "first.md"
    assert len(list((tmp_path / "uploads").iterdir())) == 1
    get_settings.cache_clear()
