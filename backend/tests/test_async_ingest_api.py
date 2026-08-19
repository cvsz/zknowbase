from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.queue_routes import router
from app.core.config import get_settings
from app.store_factory import document_store


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("ZKB_API_KEY", "this-is-a-test-secret-key")
    monkeypatch.setenv("ZKB_METADATA_BACKEND", "sqlite")
    monkeypatch.setenv("ZKB_METADATA_DB", str(tmp_path / "zknowbase.db"))
    monkeypatch.setenv("ZKB_UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    settings = get_settings()
    settings.ensure_paths()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def test_async_file_enqueue_list_and_cancel(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"X-API-Key": "this-is-a-test-secret-key"}

    response = client.post(
        "/api/v1/ingest/async",
        headers=headers,
        files={"file": ("policy.md", b"# Leave policy\nEmployees receive leave.", "text/markdown")},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["document"]["status"] == "queued"
    assert payload["job"]["status"] == "queued"
    job_id = payload["job"]["id"]
    doc_id = payload["document"]["id"]

    jobs = client.get("/api/v1/ingest/jobs", headers=headers)
    assert jobs.status_code == 200
    assert any(item["id"] == job_id for item in jobs.json())

    cancelled = client.delete(f"/api/v1/ingest/jobs/{job_id}", headers=headers)
    assert cancelled.status_code == 204

    settings = get_settings()
    record = document_store(settings).get(doc_id)
    assert record is not None
    assert record.status == "cancelled"
    assert not (tmp_path / "uploads" / f"{doc_id}.md").exists()
    get_settings.cache_clear()


def test_async_url_is_queued_without_network_fetch(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"X-API-Key": "this-is-a-test-secret-key"}
    response = client.post(
        "/api/v1/ingest/url/async",
        headers=headers,
        json={"url": "https://example.com/manual"},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["document"]["source_type"] == "url"
    assert payload["document"]["status"] == "queued"
    assert payload["job"]["source_uri"] == "https://example.com/manual"
    get_settings.cache_clear()
