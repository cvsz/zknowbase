import json
from pathlib import Path

import httpx
import pytest

from app.backup import QdrantSnapshots, sha256_file
from app.core.config import Settings


@pytest.mark.asyncio
async def test_qdrant_snapshot_download_cleanup_and_restore(tmp_path: Path):
    calls: list[tuple[str, str, str]] = []
    snapshot_bytes = b"snapshot-bytes"

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, request.url.query.decode()))
        if request.method == "GET" and request.url.path == "/":
            return httpx.Response(200, json={"version": "1.15.1"})
        if request.method == "GET" and request.url.path == "/collections/zknowbase":
            return httpx.Response(200, json={"result": {"status": "green"}})
        if request.method == "POST" and request.url.path == "/collections/zknowbase/snapshots":
            return httpx.Response(
                200,
                json={"result": {"name": "snap.snapshot", "checksum": "server-checksum"}},
            )
        if request.method == "GET" and request.url.path.endswith("/snapshots/snap.snapshot"):
            return httpx.Response(200, content=snapshot_bytes)
        if request.method == "DELETE" and request.url.path.endswith("/snapshots/snap.snapshot"):
            return httpx.Response(200, json={"result": True})
        if request.method == "POST" and request.url.path.endswith("/snapshots/upload"):
            assert request.url.params["priority"] == "snapshot"
            assert request.url.params["checksum"] == sha256_file(output)
            return httpx.Response(200, json={"result": True})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    settings = Settings(
        api_key="this-is-a-test-secret-key",
        metadata_db=tmp_path / "db.sqlite",
        upload_dir=tmp_path / "uploads",
        backup_dir=tmp_path / "backups",
        maintenance_lock_path=tmp_path / ".lock",
        qdrant_url="http://qdrant.test",
    )
    client = QdrantSnapshots(settings, transport=httpx.MockTransport(handler))
    assert await client.version() == "1.15.1"
    output = tmp_path / "qdrant.snapshot"
    info = await client.create_download(output)
    assert info is not None
    assert output.read_bytes() == snapshot_bytes
    assert info["sha256"] == sha256_file(output)
    await client.restore_upload(output, sha256_file(output))

    paths = [path for _method, path, _query in calls]
    assert "/collections/zknowbase/snapshots/snap.snapshot" in paths
    assert "/collections/zknowbase/snapshots/upload" in paths


@pytest.mark.asyncio
async def test_qdrant_missing_collection_produces_no_snapshot(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/collections/zknowbase":
            return httpx.Response(404, json={"status": {"error": "not found"}})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    settings = Settings(
        api_key="this-is-a-test-secret-key",
        metadata_db=tmp_path / "db.sqlite",
        upload_dir=tmp_path / "uploads",
        backup_dir=tmp_path / "backups",
        maintenance_lock_path=tmp_path / ".lock",
        qdrant_url="http://qdrant.test",
    )
    client = QdrantSnapshots(settings, transport=httpx.MockTransport(handler))
    assert await client.create_download(tmp_path / "none.snapshot") is None
