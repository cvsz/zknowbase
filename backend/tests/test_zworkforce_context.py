from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import require_scopes, validate_zworkforce_context
from app.security_store import SecurityStore


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("ZKB_API_KEY", "this-is-a-test-secret-key")
    monkeypatch.setenv("ZKB_METADATA_DB", str(tmp_path / "security.db"))
    monkeypatch.setenv("ZKB_ENVIRONMENT", "development")
    get_settings.cache_clear()
    settings = get_settings()
    _record, raw_key = SecurityStore(settings.metadata_db).create_key(
        "zworkforce-readonly",
        ["knowledge:read"],
    )

    app = FastAPI()

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID", "generated-request-id")
        return await call_next(request)

    @app.get(
        "/knowledge",
        dependencies=[
            Depends(require_scopes("knowledge:read")),
            Depends(validate_zworkforce_context),
        ],
    )
    def knowledge(request: Request):
        context = getattr(request.state, "zworkforce_context", None)
        return {
            "governed": context is not None,
            "tenant_id": context.tenant_id if context else None,
            "actor_id": context.actor_id if context else None,
        }

    return TestClient(app), raw_key, settings


def _headers(raw_key: str) -> dict[str, str]:
    return {
        "X-API-Key": raw_key,
        "X-Request-ID": "request-123",
        "X-ZWorkforce-Context-Version": "1",
        "X-ZWorkforce-Tenant-ID": "default",
        "X-ZWorkforce-Actor-ID": "actor-7",
        "X-ZWorkforce-Agent-ID": "agent-policy",
        "X-ZWorkforce-Tool-ID": "knowledge.search",
        "X-ZWorkforce-Policy-Context": "policy-evaluation-42",
        "X-ZWorkforce-Request-ID": "request-123",
        "X-ZWorkforce-Trace-ID": "trace-abc",
    }


def test_governed_context_accepts_matching_authenticated_tenant(monkeypatch, tmp_path):
    client, raw_key, _settings = _client(monkeypatch, tmp_path)
    response = client.get("/knowledge", headers=_headers(raw_key))
    assert response.status_code == 200
    assert response.json() == {
        "governed": True,
        "tenant_id": "default",
        "actor_id": "actor-7",
    }
    get_settings.cache_clear()


def test_governed_context_rejects_cross_tenant_claim(monkeypatch, tmp_path):
    client, raw_key, settings = _client(monkeypatch, tmp_path)
    headers = _headers(raw_key)
    headers["X-ZWorkforce-Tenant-ID"] = "other-tenant"
    response = client.get("/knowledge", headers=headers)
    assert response.status_code == 403
    events = SecurityStore(settings.metadata_db).list_audit(20)
    assert any(
        event.action == "authorize"
        and event.outcome == "denied"
        and event.detail == "zworkforce tenant context mismatch"
        for event in events
    )
    get_settings.cache_clear()


def test_governed_context_requires_complete_bounded_fields(monkeypatch, tmp_path):
    client, raw_key, _settings = _client(monkeypatch, tmp_path)
    headers = _headers(raw_key)
    del headers["X-ZWorkforce-Actor-ID"]
    response = client.get("/knowledge", headers=headers)
    assert response.status_code == 400

    headers = _headers(raw_key)
    headers["X-ZWorkforce-Policy-Context"] = "x" * 257
    response = client.get("/knowledge", headers=headers)
    assert response.status_code == 400
    get_settings.cache_clear()


def test_governed_context_binds_request_id(monkeypatch, tmp_path):
    client, raw_key, _settings = _client(monkeypatch, tmp_path)
    headers = _headers(raw_key)
    headers["X-ZWorkforce-Request-ID"] = "different-request"
    response = client.get("/knowledge", headers=headers)
    assert response.status_code == 400
    get_settings.cache_clear()


def test_unmarked_sdk_request_remains_backward_compatible(monkeypatch, tmp_path):
    client, raw_key, _settings = _client(monkeypatch, tmp_path)
    response = client.get("/knowledge", headers={"X-API-Key": raw_key})
    assert response.status_code == 200
    assert response.json()["governed"] is False
    get_settings.cache_clear()
