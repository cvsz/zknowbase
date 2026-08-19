import hashlib
import json
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from app.models.schemas import AuditRecord, ServiceKeyRecord


class SecurityStore:
    """Durable service-key and security-audit storage.

    Service-key plaintext is returned exactly once at creation/rotation time. Only a
    SHA-256 digest is persisted. This is appropriate for generated high-entropy
    bearer tokens; callers must never accept user-chosen low-entropy keys.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS service_keys (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  key_prefix TEXT NOT NULL UNIQUE,
                  key_hash TEXT NOT NULL,
                  scopes TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  expires_at TEXT,
                  revoked_at TEXT,
                  last_used_at TEXT,
                  rotated_from TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_service_keys_prefix
                  ON service_keys(key_prefix);

                CREATE TABLE IF NOT EXISTS security_audit (
                  id TEXT PRIMARY KEY,
                  principal_id TEXT,
                  key_prefix TEXT,
                  action TEXT NOT NULL,
                  resource TEXT NOT NULL,
                  outcome TEXT NOT NULL,
                  detail TEXT,
                  created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_security_audit_created
                  ON security_audit(created_at DESC);
                """
            )
            conn.commit()

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def token_prefix(raw_key: str) -> str | None:
        prefix, separator, _secret = raw_key.partition(".")
        if not separator or not prefix.startswith("zkb_"):
            return None
        return prefix

    @staticmethod
    def _digest(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_time(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _new_material() -> tuple[str, str, str]:
        prefix = f"zkb_{uuid4().hex[:12]}"
        raw_key = f"{prefix}.{secrets.token_urlsafe(32)}"
        return prefix, raw_key, SecurityStore._digest(raw_key)

    def create_key(
        self,
        name: str,
        scopes: list[str],
        expires_at: datetime | None = None,
        *,
        rotated_from: str | None = None,
    ) -> tuple[ServiceKeyRecord, str]:
        key_id = str(uuid4())
        prefix, raw_key, key_hash = self._new_material()
        created_at = self.now()
        expires_at = self._normalize_time(expires_at)
        normalized_scopes = sorted(set(scopes))
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO service_keys
                (id,name,key_prefix,key_hash,scopes,created_at,expires_at,revoked_at,last_used_at,rotated_from)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    key_id,
                    name,
                    prefix,
                    key_hash,
                    json.dumps(normalized_scopes),
                    created_at.isoformat(),
                    expires_at.isoformat() if expires_at else None,
                    None,
                    None,
                    rotated_from,
                ),
            )
            conn.commit()
        record = ServiceKeyRecord(
            id=key_id,
            name=name,
            key_prefix=prefix,
            scopes=normalized_scopes,
            created_at=created_at,
            expires_at=expires_at,
            revoked_at=None,
            last_used_at=None,
            rotated_from=rotated_from,
        )
        return record, raw_key

    def verify(self, raw_key: str) -> ServiceKeyRecord | None:
        prefix = self.token_prefix(raw_key)
        if not prefix:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM service_keys WHERE key_prefix=?",
                (prefix,),
            ).fetchone()
            if not row or not secrets.compare_digest(row["key_hash"], self._digest(raw_key)):
                return None
            record = self._to_key_record(row)
            now = self.now()
            if record.revoked_at is not None:
                return None
            if record.expires_at is not None and record.expires_at <= now:
                return None

            if record.last_used_at is None or record.last_used_at <= now - timedelta(minutes=5):
                conn.execute(
                    "UPDATE service_keys SET last_used_at=? WHERE id=?",
                    (now.isoformat(), record.id),
                )
                conn.commit()
                record.last_used_at = now
            return record

    def get_key(self, key_id: str) -> ServiceKeyRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM service_keys WHERE id=?", (key_id,)).fetchone()
        return self._to_key_record(row) if row else None

    def list_keys(self) -> list[ServiceKeyRecord]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM service_keys ORDER BY created_at DESC").fetchall()
        return [self._to_key_record(row) for row in rows]

    def revoke(self, key_id: str) -> bool:
        now = self.now().isoformat()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE service_keys SET revoked_at=COALESCE(revoked_at, ?) WHERE id=?",
                (now, key_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def rotate(self, key_id: str) -> tuple[ServiceKeyRecord, str] | None:
        new_id = str(uuid4())
        prefix, raw_key, key_hash = self._new_material()
        created_at = self.now()
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM service_keys WHERE id=?", (key_id,)).fetchone()
            if not row:
                conn.rollback()
                return None
            old = self._to_key_record(row)
            if old.revoked_at is not None:
                conn.rollback()
                return None
            if old.expires_at is not None and old.expires_at <= created_at:
                conn.rollback()
                return None
            revoked = conn.execute(
                "UPDATE service_keys SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
                (created_at.isoformat(), old.id),
            )
            if revoked.rowcount != 1:
                conn.rollback()
                return None
            conn.execute(
                """
                INSERT INTO service_keys
                (id,name,key_prefix,key_hash,scopes,created_at,expires_at,revoked_at,last_used_at,rotated_from)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    new_id,
                    old.name,
                    prefix,
                    key_hash,
                    json.dumps(sorted(set(old.scopes))),
                    created_at.isoformat(),
                    old.expires_at.isoformat() if old.expires_at else None,
                    None,
                    None,
                    old.id,
                ),
            )
            conn.commit()
        record = ServiceKeyRecord(
            id=new_id,
            name=old.name,
            key_prefix=prefix,
            scopes=sorted(set(old.scopes)),
            created_at=created_at,
            expires_at=old.expires_at,
            revoked_at=None,
            last_used_at=None,
            rotated_from=old.id,
        )
        return record, raw_key

    def audit(
        self,
        principal_id: str | None,
        key_prefix: str | None,
        action: str,
        resource: str,
        outcome: str,
        detail: str | None = None,
    ) -> AuditRecord:
        record = AuditRecord(
            id=str(uuid4()),
            principal_id=principal_id,
            key_prefix=key_prefix,
            action=action,
            resource=resource,
            outcome=outcome,
            detail=detail,
            created_at=self.now(),
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO security_audit
                (id,principal_id,key_prefix,action,resource,outcome,detail,created_at)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    record.id,
                    record.principal_id,
                    record.key_prefix,
                    record.action,
                    record.resource,
                    record.outcome,
                    record.detail,
                    record.created_at.isoformat(),
                ),
            )
            conn.commit()
        return record

    def list_audit(self, limit: int = 100) -> list[AuditRecord]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM security_audit ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [AuditRecord(**dict(row)) for row in rows]

    @staticmethod
    def _to_key_record(row: sqlite3.Row) -> ServiceKeyRecord:
        return ServiceKeyRecord(
            id=row["id"],
            name=row["name"],
            key_prefix=row["key_prefix"],
            scopes=json.loads(row["scopes"]),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
            last_used_at=row["last_used_at"],
            rotated_from=row["rotated_from"],
        )
