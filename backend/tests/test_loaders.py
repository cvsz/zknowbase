import socket

import pytest

from app.core.config import Settings
from app.rag.loaders import _assert_public_host, parse_bytes


def test_parse_bytes_rejects_unsupported_extension() -> None:
    with pytest.raises(ValueError, match="Unsupported file type"):
        parse_bytes("payload.exe", b"not allowed")


def test_parse_bytes_accepts_markdown() -> None:
    assert parse_bytes("policy.md", b"# Leave\n30 days") == "# Leave\n30 days"


def test_public_host_guard_rejects_private_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    def private_resolution(hostname: str, port: int | None):
        del hostname, port
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", private_resolution)
    with pytest.raises(ValueError, match="non-public address"):
        _assert_public_host("example.test")


def test_production_rejects_default_api_key() -> None:
    with pytest.raises(ValueError, match="ZKB_API_KEY must be replaced"):
        Settings(environment="production")
