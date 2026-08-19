import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.backup_crypto import (
    BackupCryptoError,
    decrypt_archive,
    encrypt_archive,
    is_encrypted_archive,
    load_key_file,
)
from app.core.config import Settings, get_settings
from app.maintenance import mutation_lock
from app.store_factory import document_store, ingestion_queue, security_store

FORMAT_VERSION = 1
POSTGRES_REQUIRED_TABLES = (
    "documents",
    "service_keys",
    "security_audit",
    "ingestion_jobs",
)
POSTGRES_TENANT_MAPPING_TABLES = (
    "service_key_tenants",
    "ingestion_job_tenants",
)
POSTGRES_TABLES = POSTGRES_REQUIRED_TABLES + POSTGRES_TENANT_MAPPING_TABLES


class BackupError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    raise TypeError(f"Unsupported backup value: {type(value)!r}")


def _backup_key(settings: Settings) -> bytes | None:
    if settings.backup_encryption_key_file is None:
        if settings.backup_require_encryption:
            raise BackupError("Backup encryption is required but no key file is configured")
        return None
    try:
        return load_key_file(settings.backup_encryption_key_file)
    except BackupCryptoError as exc:
        raise BackupError(str(exc)) from exc


@contextmanager
def _readable_archive(settings: Settings, archive: Path, temp_root: Path) -> Iterator[Path]:
    if not is_encrypted_archive(archive):
        if settings.backup_require_encryption:
            raise BackupError("Unencrypted backup rejected by encryption policy")
        yield archive
        return
    key = _backup_key(settings)
    if key is None:
        raise BackupError("Encrypted backup requires ZKB_BACKUP_ENCRYPTION_KEY_FILE")
    plain = temp_root / "decrypted-backup.tar.gz"
    try:
        decrypt_archive(archive, plain, key)
    except BackupCryptoError as exc:
        raise BackupError(str(exc)) from exc
    try:
        yield plain
    finally:
        plain.unlink(missing_ok=True)


def _safe_member_path(root: Path, member_name: str) -> Path:
    if not member_name or member_name.startswith(("/", "\\")):
        raise BackupError("Archive contains an absolute path")
    candidate = (root / member_name).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise BackupError("Archive path escapes the restore directory")
    return candidate


def _safe_extract_archive(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            _safe_member_path(destination, member.name)
            if member.issym() or member.islnk() or member.isdev():
                raise BackupError("Archive contains an unsafe link/device member")
        tar.extractall(destination, filter="data")


def _archive_uploads(upload_dir: Path, output: Path) -> None:
    with tarfile.open(output, "w:gz") as tar:
        if not upload_dir.exists():
            return
        for path in sorted(upload_dir.rglob("*")):
            if path.is_symlink():
                raise BackupError(f"Upload directory contains symlink: {path}")
            if path.is_file():
                tar.add(path, arcname=path.relative_to(upload_dir), recursive=False)


def _restore_uploads(archive: Path, upload_dir: Path) -> None:
    parent = upload_dir.parent
    staging = parent / f".uploads-restore-{uuid4().hex}"
    previous = parent / f".uploads-previous-{uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        _safe_extract_archive(archive, staging)
        if upload_dir.exists():
            upload_dir.rename(previous)
        staging.rename(upload_dir)
        if previous.exists():
            shutil.rmtree(previous)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if previous.exists() and not upload_dir.exists():
            previous.rename(upload_dir)
        raise


def _backup_sqlite(settings: Settings, output: Path) -> None:
    source = sqlite3.connect(settings.metadata_db, timeout=30)
    destination = sqlite3.connect(output)
    try:
        source.backup(destination)
        check = destination.execute("PRAGMA integrity_check").fetchone()
        if not check or check[0] != "ok":
            raise BackupError("SQLite backup failed integrity_check")
    finally:
        destination.close()
        source.close()


def _restore_sqlite(settings: Settings, source_path: Path) -> None:
    source = sqlite3.connect(source_path)
    destination = sqlite3.connect(settings.metadata_db, timeout=30)
    try:
        check = source.execute("PRAGMA integrity_check").fetchone()
        if not check or check[0] != "ok":
            raise BackupError("Backup SQLite database failed integrity_check")
        source.backup(destination)
        destination.commit()
    finally:
        destination.close()
        source.close()


def _backup_postgres(settings: Settings, output: Path) -> None:
    assert settings.postgres_url
    payload: dict[str, Any] = {"format_version": 1, "tables": {}}
    with psycopg.connect(settings.postgres_url, row_factory=dict_row) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            for table in POSTGRES_TABLES:
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()
                payload["tables"][table] = rows
    output.write_text(json.dumps(payload, default=_json_default, sort_keys=True), encoding="utf-8")


def _restore_postgres(settings: Settings, source_path: Path) -> None:
    assert settings.postgres_url
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if payload.get("format_version") != 1 or not isinstance(payload.get("tables"), dict):
        raise BackupError("Unsupported Postgres metadata backup format")

    tables = payload["tables"]
    document_store(settings)
    security_store(settings)
    ingestion_queue(settings)

    with psycopg.connect(settings.postgres_url, row_factory=dict_row) as conn:
        with conn.transaction():
            conn.execute(
                "TRUNCATE ingestion_job_tenants, service_key_tenants, "
                "ingestion_jobs, security_audit, service_keys, documents"
            )
            for table in POSTGRES_TABLES:
                rows = tables.get(table)
                if rows is None and table in POSTGRES_TENANT_MAPPING_TABLES:
                    continue
                if not isinstance(rows, list):
                    raise BackupError(f"Missing Postgres table backup: {table}")
                for row in rows:
                    if not isinstance(row, dict) or not row:
                        raise BackupError(f"Invalid row in Postgres table backup: {table}")
                    columns = list(row)
                    values = [row[column] for column in columns]
                    if table == "service_keys" and "scopes" in columns:
                        index = columns.index("scopes")
                        values[index] = Jsonb(values[index])
                    placeholders = ",".join(["%s"] * len(columns))
                    names = ",".join(columns)
                    conn.execute(f"INSERT INTO {table} ({names}) VALUES ({placeholders})", values)


class QdrantSnapshots:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    async def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.qdrant_url.rstrip("/"),
            timeout=self.settings.request_timeout_seconds,
            transport=self.transport,
        )

    async def version(self) -> str:
        async with await self._client() as client:
            response = await client.get("/")
            response.raise_for_status()
            value = response.json().get("version")
            if not isinstance(value, str):
                raise BackupError("Qdrant version response is invalid")
            return value

    async def collection_exists(self) -> bool:
        async with await self._client() as client:
            response = await client.get(f"/collections/{self.settings.qdrant_collection}")
            if response.status_code == 404:
                return False
            response.raise_for_status()
            return True

    async def create_download(self, output: Path) -> dict[str, Any] | None:
        if not await self.collection_exists():
            return None
        collection = self.settings.qdrant_collection
        async with await self._client() as client:
            created = await client.post(
                f"/collections/{collection}/snapshots", params={"wait": "true"}
            )
            created.raise_for_status()
            result = created.json().get("result")
            if not isinstance(result, dict) or not isinstance(result.get("name"), str):
                raise BackupError("Qdrant snapshot creation response is invalid")
            name = result["name"]
            try:
                download = await client.get(f"/collections/{collection}/snapshots/{name}")
                download.raise_for_status()
                output.write_bytes(download.content)
            finally:
                cleanup = await client.delete(
                    f"/collections/{collection}/snapshots/{name}", params={"wait": "true"}
                )
                cleanup.raise_for_status()
            return {
                "name": name,
                "server_checksum": result.get("checksum"),
                "sha256": sha256_file(output),
                "size": output.stat().st_size,
            }

    async def restore_upload(self, snapshot: Path, checksum: str) -> None:
        collection = self.settings.qdrant_collection
        async with await self._client() as client:
            with snapshot.open("rb") as handle:
                response = await client.post(
                    f"/collections/{collection}/snapshots/upload",
                    params={"wait": "true", "priority": "snapshot", "checksum": checksum},
                    files={"snapshot": (snapshot.name, handle, "application/octet-stream")},
                )
            response.raise_for_status()
            if response.json().get("result") is not True:
                raise BackupError("Qdrant snapshot restore did not report success")

    async def delete_collection(self) -> None:
        async with await self._client() as client:
            response = await client.delete(f"/collections/{self.settings.qdrant_collection}")
            if response.status_code != 404:
                response.raise_for_status()


def _version_minor(version: str) -> tuple[int, int]:
    try:
        major, minor, *_rest = version.split(".")
        return int(major), int(minor)
    except (TypeError, ValueError) as exc:
        raise BackupError(f"Invalid Qdrant version: {version}") from exc


def _write_manifest(
    workdir: Path,
    settings: Settings,
    qdrant_version: str,
    qdrant: dict[str, Any] | None,
) -> dict[str, Any]:
    component_names = ["uploads.tar.gz"]
    metadata_name = (
        "metadata.sqlite" if settings.metadata_backend == "sqlite" else "metadata.postgres.json"
    )
    component_names.append(metadata_name)
    if qdrant is not None:
        component_names.append("qdrant.snapshot")
    components = {
        name: {"sha256": sha256_file(workdir / name), "size": (workdir / name).stat().st_size}
        for name in component_names
    }
    manifest = {
        "format_version": FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metadata_backend": settings.metadata_backend,
        "qdrant": {
            "collection": settings.qdrant_collection,
            "version": qdrant_version,
            "snapshot": qdrant,
        },
        "components": components,
    }
    (workdir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest


def _verify_workdir(workdir: Path) -> dict[str, Any]:
    manifest_path = workdir / "manifest.json"
    if not manifest_path.is_file():
        raise BackupError("Backup manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != FORMAT_VERSION:
        raise BackupError("Unsupported backup format version")
    components = manifest.get("components")
    if not isinstance(components, dict):
        raise BackupError("Backup component manifest is invalid")
    allowed = {"manifest.json", *components.keys()}
    actual = {path.name for path in workdir.iterdir()}
    if actual != allowed:
        raise BackupError("Backup archive contains unexpected or missing files")
    for name, info in components.items():
        path = workdir / name
        if not path.is_file() or not isinstance(info, dict):
            raise BackupError(f"Backup component is missing: {name}")
        if path.stat().st_size != info.get("size") or sha256_file(path) != info.get("sha256"):
            raise BackupError(f"Backup checksum verification failed: {name}")
    return manifest


async def create_backup(
    settings: Settings,
    output: Path | None = None,
    *,
    lock: bool = True,
) -> Path:
    settings.ensure_paths()
    key = _backup_key(settings)
    if output is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix = ".zkb" if key is not None else ".tar.gz"
        output = settings.backup_dir / f"zknowbase-{timestamp}{suffix}"
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise BackupError(f"Backup already exists: {output}")

    def _metadata_and_uploads(workdir: Path) -> None:
        if settings.metadata_backend == "sqlite":
            _backup_sqlite(settings, workdir / "metadata.sqlite")
        else:
            _backup_postgres(settings, workdir / "metadata.postgres.json")
        _archive_uploads(settings.upload_dir, workdir / "uploads.tar.gz")

    lock_context = mutation_lock(settings.maintenance_lock_path, exclusive=True)
    if lock:
        lock_context.__enter__()
    try:
        with tempfile.TemporaryDirectory(prefix="zkb-backup-") as raw:
            workdir = Path(raw)
            _metadata_and_uploads(workdir)
            qdrant_client = QdrantSnapshots(settings)
            version = await qdrant_client.version()
            snapshot = await qdrant_client.create_download(workdir / "qdrant.snapshot")
            _write_manifest(workdir, settings, version, snapshot)
            plain_archive = workdir / "backup.tar.gz"
            with tarfile.open(plain_archive, "w:gz") as tar:
                for path in sorted(workdir.iterdir()):
                    if path != plain_archive:
                        tar.add(path, arcname=path.name, recursive=False)
            if key is None:
                shutil.copyfile(plain_archive, output)
                os.chmod(output, 0o600)
            else:
                try:
                    encrypt_archive(plain_archive, output, key)
                except BackupCryptoError as exc:
                    output.unlink(missing_ok=True)
                    raise BackupError(str(exc)) from exc
    finally:
        if lock:
            lock_context.__exit__(None, None, None)
    return output


async def restore_backup(
    settings: Settings,
    archive: Path,
    *,
    yes: bool,
    safety_backup: bool = True,
) -> Path | None:
    if not yes:
        raise BackupError("Restore is destructive; pass --yes to continue")
    archive = archive.resolve()
    if not archive.is_file():
        raise BackupError(f"Backup archive not found: {archive}")

    with tempfile.TemporaryDirectory(prefix="zkb-restore-") as raw:
        temp_root = Path(raw)
        workdir = temp_root / "workdir"
        workdir.mkdir()
        with _readable_archive(settings, archive, temp_root) as readable:
            _safe_extract_archive(readable, workdir)
        manifest = _verify_workdir(workdir)
        if manifest.get("metadata_backend") != settings.metadata_backend:
            raise BackupError(
                "Metadata backend mismatch; restore into the same backend type used by the backup"
            )
        qdrant_manifest = manifest.get("qdrant")
        if (
            not isinstance(qdrant_manifest, dict)
            or qdrant_manifest.get("collection") != settings.qdrant_collection
        ):
            raise BackupError("Qdrant collection mismatch")

        qdrant_client = QdrantSnapshots(settings)
        current_qdrant_version = await qdrant_client.version()
        backup_qdrant_version = qdrant_manifest.get("version")
        if (
            not isinstance(backup_qdrant_version, str)
            or _version_minor(current_qdrant_version) != _version_minor(backup_qdrant_version)
        ):
            raise BackupError(
                f"Qdrant minor-version mismatch: backup={backup_qdrant_version}, "
                f"current={current_qdrant_version}"
            )

        with mutation_lock(settings.maintenance_lock_path, exclusive=True):
            safety_path = None
            if safety_backup:
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                suffix = ".zkb" if _backup_key(settings) is not None else ".tar.gz"
                safety_path = settings.backup_dir / f"pre-restore-{timestamp}-{uuid4().hex[:8]}{suffix}"
                await create_backup(settings, safety_path, lock=False)

            snapshot_info = qdrant_manifest.get("snapshot")
            if snapshot_info is None:
                await qdrant_client.delete_collection()
            else:
                if not isinstance(snapshot_info, dict):
                    raise BackupError("Qdrant snapshot manifest is invalid")
                await qdrant_client.restore_upload(
                    workdir / "qdrant.snapshot",
                    str(manifest["components"]["qdrant.snapshot"]["sha256"]),
                )

            _restore_uploads(workdir / "uploads.tar.gz", settings.upload_dir)
            if settings.metadata_backend == "sqlite":
                _restore_sqlite(settings, workdir / "metadata.sqlite")
            else:
                _restore_postgres(settings, workdir / "metadata.postgres.json")
            return safety_path


def verify_backup(settings: Settings, archive: Path) -> dict[str, Any]:
    archive = archive.resolve()
    if not archive.is_file():
        raise BackupError(f"Backup archive not found: {archive}")
    with tempfile.TemporaryDirectory(prefix="zkb-verify-") as raw:
        temp_root = Path(raw)
        workdir = temp_root / "workdir"
        workdir.mkdir()
        with _readable_archive(settings, archive, temp_root) as readable:
            _safe_extract_archive(readable, workdir)
        return _verify_workdir(workdir)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local zknowbase backup/restore")
    sub = parser.add_subparsers(dest="command", required=True)
    backup = sub.add_parser("backup", help="Create a verified local backup archive")
    backup.add_argument("--output", type=Path)
    restore = sub.add_parser("restore", help="Restore a verified local backup archive")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--yes", action="store_true", help="Confirm destructive restore")
    restore.add_argument("--no-safety-backup", action="store_true")
    verify = sub.add_parser("verify", help="Verify an archive without restoring it")
    verify.add_argument("archive", type=Path)
    return parser


async def _main_async() -> int:
    args = _build_parser().parse_args()
    settings = get_settings()
    if args.command == "backup":
        path = await create_backup(settings, args.output)
        print(
            json.dumps(
                {
                    "backup": str(path),
                    "sha256": sha256_file(path),
                    "encrypted": is_encrypted_archive(path),
                }
            )
        )
        return 0
    if args.command == "verify":
        manifest = verify_backup(settings, args.archive)
        print(json.dumps({"valid": True, "manifest": manifest}, sort_keys=True))
        return 0
    safety = await restore_backup(
        settings,
        args.archive,
        yes=args.yes,
        safety_backup=not args.no_safety_backup,
    )
    print(
        json.dumps(
            {
                "restored": str(args.archive.resolve()),
                "safety_backup": str(safety) if safety else None,
            }
        )
    )
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(_main_async()))
    except BackupError as exc:
        raise SystemExit(f"backup/restore error: {exc}") from exc


if __name__ == "__main__":
    main()
