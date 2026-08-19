from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.queue_routes import router as queue_router
from app.api.routes import router as core_router
from app.core.config import get_settings
from app.store_factory import document_store, security_store


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
    assert payload["document"]["tenant_id"] == "default"
    assert payload["job"]["status"] == "queued"
    assert payload["job"]["tenant_id"] == "default"
    job_id = payload["job"]["id"]
    doc_id = payload["document"]["id"]

    jobs = client.get("/api/v1/ingest/jobs", headers=headers)
    assert jobs.status_code == 200
    assert any(item["id"] == job_id for item in jobs.json())

    assert client.delete(f"/api/v1/documents/{doc_id}", headers=headers).status_code == 409
    assert client.post(f"/api/v1/documents/{doc_id}/reindex", headers=headers).status_code == 409

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


def test_async_jobs_are_tenant_scoped_and_client_cannot_forge_tenant(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    settings = get_settings()
    _record, beta_secret = security_store(settings).create_key(
        "beta-writer",
        ["knowledge:read", "knowledge:write"],
        tenant_id="beta",
    )
    beta_headers = {"X-API-Key": beta_secret}
    default_headers = {"X-API-Key": "this-is-a-test-secret-key"}

    queued = client.post(
        "/api/v1/ingest/url/async",
        headers=beta_headers,
        json={"url": "https://example.com/beta", "tenant_id": "default"},
    )
    assert queued.status_code == 202
    payload = queued.json()
    assert payload["document"]["tenant_id"] == "beta"
    assert payload["job"]["tenant_id"] == "beta"
    job_id = payload["job"]["id"]

    default_list = client.get("/api/v1/ingest/jobs", headers=default_headers)
    assert default_list.status_code == 200
    assert all(item["id"] != job_id for item in default_list.json())
    assert client.get(f"/api/v1/ingest/jobs/{job_id}", headers=default_headers).status_code == 404
    assert client.delete(f"/api/v1/ingest/jobs/{job_id}", headers=default_headers).status_code == 404

    beta_get = client.get(f"/api/v1/ingest/jobs/{job_id}", headers=beta_headers)
    assert beta_get.status_code == 200
    assert beta_get.json()["tenant_id"] == "beta"
    assert client.delete(f"/api/v1/ingest/jobs/{job_id}", headers=beta_headers).status_code == 204
    get_settings.cache_clear()


def test_async_file_rejects_unsupported_type_before_queue(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"X-API-Key": "this-is-a-test-secret-key"}
    response = client.post(
        "/api/v1/ingest/async",
        headers=headers,
        files={"file": ("malware.exe", b"not-a-document", "application/octet-stream")},
    )
    assert response.status_code == 415
    assert client.get("/api/v1/ingest/jobs", headers=headers).json() == []
    get_settings.cache_clear()
