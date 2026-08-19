import json
import tarfile
from pathlib import Path

import pytest

import app.backup as backup
from app.core.config import Settings
from app.models.schemas import DocumentRecord
from app.store import DocumentStore


class FakeQdrantSnapshots:
    restored: list[tuple[bytes, str]] = []
    deleted = False
    version_value = "1.15.1"

    def __init__(self, settings):
        self.settings = settings

    async def version(self):
        return self.version_value

    async def create_download(self, output: Path):
        output.write_bytes(b"qdrant-snapshot")
        return {
            "name": "snapshot-1",
            "server_checksum": None,
            "sha256": backup.sha256_file(output),
            "size": output.stat().st_size,
        }

    async def restore_upload(self, snapshot: Path, checksum: str):
        self.restored.append((snapshot.read_bytes(), checksum))

    async def delete_collection(self):
        self.deleted = True


def _settings(tmp_path: Path) -> Settings:
    settings = Settings(
        api_key="this-is-a-test-secret-key",
        metadata_backend="sqlite",
        metadata_db=tmp_path / "data" / "zknowbase.db",
        upload_dir=tmp_path / "data" / "uploads",
        backup_dir=tmp_path / "data" / "backups",
        maintenance_lock_path=tmp_path / "data" / ".mutation.lock",
        qdrant_url="http://qdrant.invalid:6333",
    )
    settings.ensure_paths()
    return settings


def _seed(settings: Settings) -> str:
    store = DocumentStore(settings.metadata_db)
    now = store.now()
    doc_id = "doc-1"
    upload = settings.upload_dir / f"{doc_id}.md"
    upload.write_text("original knowledge", encoding="utf-8")
    store.upsert(
        DocumentRecord(
            id=doc_id,
            name="policy.md",
            source_type="file",
            source_uri=str(upload),
            content_type="text/markdown",
            status="ready",
            chunk_count=2,
            size_bytes=upload.stat().st_size,
            created_at=now,
            updated_at=now,
        )
    )
    return doc_id


@pytest.mark.asyncio
async def test_sqlite_backup_restore_round_trip(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    doc_id = _seed(settings)
    FakeQdrantSnapshots.restored.clear()
    monkeypatch.setattr(backup, "QdrantSnapshots", FakeQdrantSnapshots)

    archive = await backup.create_backup(settings)
    assert archive.is_file()
    assert archive.stat().st_mode & 0o077 == 0

    DocumentStore(settings.metadata_db).delete(doc_id)
    (settings.upload_dir / f"{doc_id}.md").write_text("changed", encoding="utf-8")

    safety = await backup.restore_backup(settings, archive, yes=True, safety_backup=False)
    assert safety is None
    restored = DocumentStore(settings.metadata_db).get(doc_id)
    assert restored is not None
    assert restored.name == "policy.md"
    assert (settings.upload_dir / f"{doc_id}.md").read_text(encoding="utf-8") == "original knowledge"
    assert FakeQdrantSnapshots.restored
    data, checksum = FakeQdrantSnapshots.restored[-1]
    assert data == b"qdrant-snapshot"
    assert checksum == backup.sha256_file(_extract_component(archive, tmp_path, "qdrant.snapshot"))


def _extract_component(archive: Path, tmp_path: Path, name: str) -> Path:
    destination = tmp_path / f"extract-{name.replace('.', '-') }"
    destination.mkdir()
    backup._safe_extract_archive(archive, destination)
    return destination / name


@pytest.mark.asyncio
async def test_restore_rejects_qdrant_minor_version_mismatch(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    _seed(settings)
    monkeypatch.setattr(backup, "QdrantSnapshots", FakeQdrantSnapshots)
    FakeQdrantSnapshots.version_value = "1.15.1"
    archive = await backup.create_backup(settings)
    FakeQdrantSnapshots.version_value = "1.16.0"
    try:
        with pytest.raises(backup.BackupError, match="minor-version mismatch"):
            await backup.restore_backup(settings, archive, yes=True, safety_backup=False)
    finally:
        FakeQdrantSnapshots.version_value = "1.15.1"


@pytest.mark.asyncio
async def test_restore_rejects_corrupted_component_before_mutation(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    _seed(settings)
    monkeypatch.setattr(backup, "QdrantSnapshots", FakeQdrantSnapshots)
    archive = await backup.create_backup(settings)

    unpacked = tmp_path / "tampered"
    unpacked.mkdir()
    backup._safe_extract_archive(archive, unpacked)
    (unpacked / "uploads.tar.gz").write_bytes(b"tampered")
    tampered = tmp_path / "tampered.tar.gz"
    with tarfile.open(tampered, "w:gz") as tar:
        for path in sorted(unpacked.iterdir()):
            tar.add(path, arcname=path.name, recursive=False)

    with pytest.raises(backup.BackupError, match="checksum"):
        await backup.restore_backup(settings, tampered, yes=True, safety_backup=False)


def test_backup_manifest_contains_only_checksums_not_secrets(tmp_path):
    settings = _settings(tmp_path)
    _seed(settings)
    workdir = tmp_path / "work"
    workdir.mkdir()
    backup._backup_sqlite(settings, workdir / "metadata.sqlite")
    backup._archive_uploads(settings.upload_dir, workdir / "uploads.tar.gz")
    manifest = backup._write_manifest(workdir, settings, "1.15.1", None)
    encoded = json.dumps(manifest)
    assert settings.api_key not in encoded
    assert set(manifest["components"]) == {"metadata.sqlite", "uploads.tar.gz"}
