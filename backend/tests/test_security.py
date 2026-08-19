from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.security import require_api_key


def test_api_key_rejected_without_header(monkeypatch):
    monkeypatch.setenv("ZKB_API_KEY", "this-is-a-test-secret-key")
    from app.core.config import get_settings
    get_settings.cache_clear()
    app = FastAPI()

    @app.get("/secure", dependencies=[Depends(require_api_key)])
    def secure():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/secure").status_code == 401
    assert client.get("/secure", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/secure", headers={"X-API-Key": "this-is-a-test-secret-key"}).status_code == 200
    get_settings.cache_clear()
