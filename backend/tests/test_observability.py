from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.observability as observability
from app.core.config import Settings
from app.main import app


def _settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "api_key": "this-is-a-test-secret-key",
        "metadata_db": tmp_path / "zknowbase.db",
        "upload_dir": tmp_path / "uploads",
        "backup_dir": tmp_path / "backups",
        "maintenance_lock_path": tmp_path / ".lock",
    }
    values.update(overrides)
    settings = Settings(**values)
    settings.ensure_paths()
    return settings


def test_metrics_endpoint_exposes_bounded_zknowbase_metrics():
    client = TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "zkb_http_requests_total" in body
    assert "zkb_http_request_duration_seconds" in body
    assert "zkb_query_duration_seconds" in body
    assert "zkb_search_duration_seconds" in body
    assert "zkb_ingestion_queue_depth" in body
    assert "zkb_auth_failures_total" in body
    assert "zkb_authorization_denials_total" in body
    assert "zkb_qdrant_errors_total" in body
    assert "X-API-Key" not in body


def test_metrics_disabled_returns_not_found(monkeypatch):
    monkeypatch.setattr("app.main.settings.metrics_enabled", False)
    try:
        response = TestClient(app).get("/metrics")
        assert response.status_code == 404
    finally:
        monkeypatch.setattr("app.main.settings.metrics_enabled", True)


def test_invalid_otlp_endpoint_fails_configuration_closed(tmp_path):
    with pytest.raises(ValueError, match="OTLP_ENDPOINT"):
        _settings(tmp_path, otel_exporter_otlp_endpoint="file:///tmp/traces")


def test_tracing_initialization_failure_does_not_break_core(monkeypatch, tmp_path):
    settings = _settings(tmp_path, otel_exporter_otlp_endpoint="http://collector.invalid:4318")
    monkeypatch.setattr(observability, "_tracing_configured", False)

    class BrokenExporter:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("collector unavailable")

    monkeypatch.setattr(observability, "OTLPSpanExporter", BrokenExporter)
    observability.configure_tracing(settings)
    assert observability._tracing_configured is False
