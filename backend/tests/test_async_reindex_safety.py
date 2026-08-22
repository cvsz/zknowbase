from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.queue_routes import router as queue_router
from app.api.routes import router as core_router
from app.core.config import get_settings
from app.models.schemas import DocumentRecord
from app.store_factory import document_store
from app.tenant_queue_store import TenantIngestionQueue


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("ZKB_API_KEY", "this-is-a-test-secret-key")
    monkeypatch.setenv("ZKB_METADATA_BACKEND", "sqlite")
    monkeypatch.setenv("ZKB_METADATA_DB", str(tmp_path / "zknowbase.db"))
    monkeypatch.setenv("ZKB_UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    settings = get_settings()
    settings.ensure_paths()
    app = FastAPI()
    app.include_router(core_router, prefix="/api/v1")
    app.include_router(queue_router, prefix="/api/v1")
    return TestClient(app)


def _ready_file_document(tmp_path) -> DocumentRecord:
    source = tmp_path / "uploads" / "manual.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Manual\nStable source", encoding="utf-8")
    now = datetime.now(timezone.utc)
    return DocumentRecord(
        id="doc-safe-reindex",
        name="manual.md",
        tenant_id="default",
        source_type="file",
        source_uri=str(source),
        content_type="text/markdown",
        status="ready",
        chunk_count=3,
        size_bytes=source.stat().st_size,
        created_at=now,
        updated_at=now,
        error="prior warning",
    )


def test_cancel_scheduled_reindex_restores_prior_state_and_keeps_source(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    settings = get_settings()
    docs = document_store(settings)
    original = _ready_file_document(tmp_path)
    docs.upsert(original)

    queued = client.post(
        "/api/v1/documents/doc-safe-reindex/reindex/async",
        headers={"X-API-Key": "this-is-a-test-secret-key"},
        json={"run_after_seconds": 3600},
    )
    assert queued.status_code == 202
    job_id = queued.json()["job"]["id"]

    cancelled = client.delete(
        f"/api/v1/ingest/jobs/{job_id}",
        headers={"X-API-Key": "this-is-a-test-secret-key"},
    )
    assert cancelled.status_code == 204

    restored = docs.get(original.id)
    assert restored is not None
    assert restored.status == original.status
    assert restored.error == original.error
    assert restored.updated_at == original.updated_at
    assert original.source_uri is not None
    assert (tmp_path / "uploads" / "manual.md").exists()
    get_settings.cache_clear()


def test_reindex_enqueue_failure_restores_exact_prior_document_state(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    settings = get_settings()
    docs = document_store(settings)
    original = _ready_file_document(tmp_path)
    docs.upsert(original)

    def fail_enqueue(self, *args, **kwargs):
        raise RuntimeError("simulated durable queue failure")

    monkeypatch.setattr(TenantIngestionQueue, "enqueue_if_inactive", fail_enqueue)
    response = client.post(
        "/api/v1/documents/doc-safe-reindex/reindex/async",
        headers={"X-API-Key": "this-is-a-test-secret-key"},
        json={"run_after_seconds": 0},
    )

    assert response.status_code == 503
    restored = docs.get(original.id)
    assert restored is not None
    assert restored.status == original.status
    assert restored.error == original.error
    assert restored.updated_at == original.updated_at
    assert original.source_uri is not None
    assert (tmp_path / "uploads" / "manual.md").exists()
    get_settings.cache_clear()
