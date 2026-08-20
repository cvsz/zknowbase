import threading
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.routes as routes
from app.api.routes import router as core_router
from app.content_identity import file_document_id, sha256_content
from app.core.config import get_settings
from app.models.schemas import DocumentRecord
from app.store_factory import document_store


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


def test_sync_concurrent_duplicate_indexes_only_once(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"X-API-Key": "this-is-a-test-secret-key"}
    content = b"# Concurrent identity\nOnly the reservation owner may index these bytes."
    entered = threading.Event()
    release = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    async def blocking_index(record, text, settings):
        nonlocal calls
        with calls_lock:
            calls += 1
        entered.set()
        assert release.wait(timeout=5)
        record.status = "ready"
        record.chunk_count = 1
        record.updated_at = routes.utcnow()
        return routes.document_store(settings).upsert(record)

    monkeypatch.setattr(routes, "index_document", blocking_index)
    first_result = {}

    def first_request():
        first_result["response"] = client.post(
            "/api/v1/ingest",
            headers=headers,
            files={"file": ("first.md", content, "text/markdown")},
        )

    thread = threading.Thread(target=first_request)
    thread.start()
    assert entered.wait(timeout=5)
    duplicate = client.post(
        "/api/v1/ingest",
        headers=headers,
        files={"file": ("second.md", content, "text/markdown")},
    )
    release.set()
    thread.join(timeout=5)

    assert duplicate.status_code == 200
    assert duplicate.json()["document"]["status"] == "processing"
    assert first_result["response"].status_code == 200
    assert calls == 1
    assert len(list((tmp_path / "uploads").iterdir())) == 1
    get_settings.cache_clear()


def test_sync_retry_reuses_existing_source_path(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    settings = get_settings()
    headers = {"X-API-Key": "this-is-a-test-secret-key"}
    content = b"retryable text content"
    doc_id = file_document_id("default", sha256_content(content))
    old_path = tmp_path / "uploads" / f"{doc_id}.txt"
    old_path.write_bytes(content)
    now = datetime.now(timezone.utc)
    document_store(settings).upsert(
        DocumentRecord(
            id=doc_id,
            name="original.txt",
            tenant_id="default",
            source_type="file",
            source_uri=str(old_path),
            content_type="text/plain",
            status="failed",
            size_bytes=len(content),
            created_at=now,
            updated_at=now,
            error="transient",
        )
    )

    response = client.post(
        "/api/v1/ingest",
        headers=headers,
        files={"file": ("renamed.md", content, "text/markdown")},
    )

    assert response.status_code == 200
    restored = document_store(settings).get(doc_id)
    assert restored is not None
    assert restored.source_uri == str(old_path)
    assert old_path.exists()
    assert len(list((tmp_path / "uploads").iterdir())) == 1
    get_settings.cache_clear()


def test_sync_file_ingestion_fails_closed_on_cross_tenant_identity_collision(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    settings = get_settings()
    content = b"# Collision sentinel\nThis row belongs to another tenant."
    doc_id = file_document_id("default", sha256_content(content))
    now = datetime.now(timezone.utc)
    document_store(settings).upsert(
        DocumentRecord(
            id=doc_id,
            name="foreign.md",
            tenant_id="beta",
            source_type="file",
            source_uri=str(tmp_path / "uploads" / f"{doc_id}.md"),
            content_type="text/markdown",
            status="ready",
            chunk_count=1,
            size_bytes=len(content),
            created_at=now,
            updated_at=now,
        )
    )

    response = client.post(
        "/api/v1/ingest",
        headers={"X-API-Key": "this-is-a-test-secret-key"},
        files={"file": ("collision.md", content, "text/markdown")},
    )

    assert response.status_code == 409
    restored = document_store(settings).get(doc_id)
    assert restored is not None
    assert restored.tenant_id == "beta"
    get_settings.cache_clear()
