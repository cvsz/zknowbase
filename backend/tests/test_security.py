from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import Principal, require_api_key, require_scopes
from app.security_store import SecurityStore


def _configure(monkeypatch, tmp_path):
    monkeypatch.setenv("ZKB_API_KEY", "this-is-a-test-secret-key")
    monkeypatch.setenv("ZKB_METADATA_DB", str(tmp_path / "security.db"))
    monkeypatch.setenv("ZKB_ENVIRONMENT", "development")
    get_settings.cache_clear()
    return get_settings()


def test_api_key_rejected_without_header(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    app = FastAPI()

    @app.get("/secure", dependencies=[Depends(require_api_key)])
    def secure():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/secure").status_code == 401
    assert client.get("/secure", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/secure", headers={"X-API-Key": "this-is-a-test-secret-key"}).status_code == 200
    get_settings.cache_clear()


def test_scoped_service_key_enforces_read_write_boundary(monkeypatch, tmp_path):
    settings = _configure(monkeypatch, tmp_path)
    service_key, raw_key = SecurityStore(settings.metadata_db).create_key(
        "zworkforce-readonly",
        ["knowledge:read"],
    )
    app = FastAPI()

    @app.get("/read", dependencies=[Depends(require_scopes("knowledge:read"))])
    def read():
        return {"ok": True}

    @app.post("/write", dependencies=[Depends(require_scopes("knowledge:write"))])
    def write():
        return {"ok": True}

    @app.get("/whoami")
    def whoami(principal: Principal = Depends(require_api_key)):
        return {"tenant_id": principal.tenant_id, "principal_id": principal.id}

    client = TestClient(app)
    headers = {"X-API-Key": raw_key}
    assert client.get("/read", headers=headers).status_code == 200
    assert client.post("/write", headers=headers).status_code == 403
    whoami = client.get("/whoami", headers=headers)
    assert whoami.status_code == 200
    assert whoami.json() == {"tenant_id": "default", "principal_id": service_key.id}

    bootstrap = {"X-API-Key": "this-is-a-test-secret-key"}
    assert client.post("/write", headers=bootstrap).status_code == 200
    assert client.get("/whoami", headers=bootstrap).json()["tenant_id"] == "default"

    audit = SecurityStore(settings.metadata_db).list_audit(20)
    assert any(
        event.principal_id == service_key.id
        and event.action == "authorize"
        and event.outcome == "denied"
        for event in audit
    )
    get_settings.cache_clear()


def test_bootstrap_key_can_be_disabled(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("ZKB_BOOTSTRAP_API_KEY_ENABLED", "false")
    get_settings.cache_clear()
    app = FastAPI()

    @app.get("/secure", dependencies=[Depends(require_api_key)])
    def secure():
        return {"ok": True}

    client = TestClient(app)
    response = client.get(
        "/secure",
        headers={"X-API-Key": "this-is-a-test-secret-key"},
    )
    assert response.status_code == 401
    get_settings.cache_clear()
