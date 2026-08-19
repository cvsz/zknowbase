import base64
import os
from pathlib import Path

import pytest

import app.backup as backup
from app.backup_crypto import MAGIC, is_encrypted_archive
from app.core.config import Settings
from app.models.schemas import DocumentRecord
from app.store import DocumentStore


class FakeQdrantSnapshots:
    restored: list[bytes] = []
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
        assert checksum == backup.sha256_file(snapshot)
        self.restored.append(snapshot.read_bytes())

    async def delete_collection(self):
        return None


def _key_file(tmp_path: Path, byte: bytes = b"k") -> Path:
    path = tmp_path / f"backup-key-{byte.hex()}"
    path.write_bytes(base64.b64encode(byte * 32))
    os.chmod(path, 0o600)
    return path


def _settings(tmp_path: Path, key_file: Path | None, *, require: bool = False) -> Settings:
    settings = Settings(
        api_key="this-is-a-test-secret-key",
        metadata_backend="sqlite",
        metadata_db=tmp_path / "data" / "zknowbase.db",
        upload_dir=tmp_path / "data" / "uploads",
        backup_dir=tmp_path / "data" / "backups",
        maintenance_lock_path=tmp_path / "data" / ".mutation.lock",
        qdrant_url="http://qdrant.invalid:6333",
        backup_encryption_key_file=key_file,
        backup_require_encryption=require,
    )
    settings.ensure_paths()
    return settings


def _seed(settings: Settings) -> None:
    store = DocumentStore(settings.metadata_db)
    now = store.now()
    upload = settings.upload_dir / "doc-enc.md"
    upload.write_text("encrypted backup knowledge", encoding="utf-8")
    store.upsert(
        DocumentRecord(
            id="doc-enc",
            name="policy.md",
            source_type="file",
            source_uri=str(upload),
            content_type="text/markdown",
            status="ready",
            chunk_count=1,
            size_bytes=upload.stat().st_size,
            created_at=now,
            updated_at=now,
        )
    )


@pytest.mark.asyncio
async def test_encrypted_backup_round_trip_and_verify(monkeypatch, tmp_path):
    settings = _settings(tmp_path, _key_file(tmp_path), require=True)
    _seed(settings)
    FakeQdrantSnapshots.restored.clear()
    monkeypatch.setattr(backup, "QdrantSnapshots", FakeQdrantSnapshots)

    archive = await backup.create_backup(settings)
    assert archive.suffix == ".zkb"
    assert is_encrypted_archive(archive)
    assert archive.read_bytes().startswith(MAGIC)
    assert archive.stat().st_mode & 0o077 == 0
    assert backup.verify_backup(settings, archive)["format_version"] == backup.FORMAT_VERSION

    DocumentStore(settings.metadata_db).delete("doc-enc")
    (settings.upload_dir / "doc-enc.md").write_text("changed", encoding="utf-8")
    await backup.restore_backup(settings, archive, yes=True, safety_backup=False)

    restored = DocumentStore(settings.metadata_db).get("doc-enc")
    assert restored is not None
    assert (settings.upload_dir / "doc-enc.md").read_text(encoding="utf-8") == "encrypted backup knowledge"
    assert FakeQdrantSnapshots.restored[-1] == b"qdrant-snapshot"


@pytest.mark.asyncio
async def test_encrypted_backup_tamper_fails_before_restore(monkeypatch, tmp_path):
    settings = _settings(tmp_path, _key_file(tmp_path), require=True)
    _seed(settings)
    monkeypatch.setattr(backup, "QdrantSnapshots", FakeQdrantSnapshots)
    archive = await backup.create_backup(settings)

    payload = bytearray(archive.read_bytes())
    payload[len(MAGIC) + 20] ^= 0x01
    tampered = tmp_path / "tampered.zkb"
    tampered.write_bytes(payload)

    with pytest.raises(backup.BackupError, match="authentication failed"):
        await backup.restore_backup(settings, tampered, yes=True, safety_backup=False)
    assert DocumentStore(settings.metadata_db).get("doc-enc") is not None


@pytest.mark.asyncio
async def test_wrong_backup_key_is_rejected(monkeypatch, tmp_path):
    settings = _settings(tmp_path, _key_file(tmp_path, b"a"), require=True)
    _seed(settings)
    monkeypatch.setattr(backup, "QdrantSnapshots", FakeQdrantSnapshots)
    archive = await backup.create_backup(settings)

    wrong = _settings(tmp_path, _key_file(tmp_path, b"b"), require=True)
    with pytest.raises(backup.BackupError, match="authentication failed"):
        backup.verify_backup(wrong, archive)


@pytest.mark.asyncio
async def test_required_encryption_rejects_plaintext_backup(monkeypatch, tmp_path):
    plaintext = _settings(tmp_path, None)
    _seed(plaintext)
    monkeypatch.setattr(backup, "QdrantSnapshots", FakeQdrantSnapshots)
    archive = await backup.create_backup(plaintext)
    assert not is_encrypted_archive(archive)

    protected = _settings(tmp_path, _key_file(tmp_path), require=True)
    with pytest.raises(backup.BackupError, match="Unencrypted backup rejected"):
        backup.verify_backup(protected, archive)


def test_backup_key_file_permissions_fail_closed(tmp_path):
    if os.name == "nt":
        pytest.skip("POSIX key-file permissions are not available on Windows")
    key_file = _key_file(tmp_path)
    os.chmod(key_file, 0o644)
    settings = _settings(tmp_path, key_file)
    with pytest.raises(backup.BackupError, match="group/world accessible"):
        backup._backup_key(settings)


def test_required_encryption_configuration_needs_key_file(tmp_path):
    with pytest.raises(ValueError, match="ZKB_BACKUP_ENCRYPTION_KEY_FILE"):
        Settings(
            api_key="this-is-a-test-secret-key",
            backup_require_encryption=True,
            metadata_db=tmp_path / "db.sqlite",
            upload_dir=tmp_path / "uploads",
        )
