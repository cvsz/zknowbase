import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.models.schemas import AuditRecord, DocumentRecord, ServiceKeyRecord


def create_postgres_pool(dsn: str, min_size: int = 1, max_size: int = 10) -> ConnectionPool:
    pool = ConnectionPool(
        dsn,
        kwargs={"row_factory": dict_row},
        min_size=min_size,
        max_size=max_size,
        open=True,
        check=ConnectionPool.check_connection,
        timeout=10.0,
    )
    pool.wait(timeout=10.0)
    return pool


class _PostgresBase:
    def __init__(self, pool: ConnectionPool):
        self.pool = pool

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)


class PostgresDocumentStore(_PostgresBase):
    def __init__(self, pool: ConnectionPool):
        super().__init__(pool)
        self._init_db()

    def _init_db(self) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  source_type TEXT NOT NULL,
                  source_uri TEXT,
                  content_type TEXT,
                  status TEXT NOT NULL,
                  chunk_count INTEGER NOT NULL DEFAULT 0,
                  size_bytes BIGINT NOT NULL DEFAULT 0,
                  created_at TIMESTAMPTZ NOT NULL,
                  updated_at TIMESTAMPTZ NOT NULL,
                  error TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at DESC)"
            )

    def upsert(self, record: DocumentRecord) -> DocumentRecord:
        data = record.model_dump()
        with self.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO documents
                (id,name,source_type,source_uri,content_type,status,chunk_count,size_bytes,created_at,updated_at,error)
                VALUES (%(id)s,%(name)s,%(source_type)s,%(source_uri)s,%(content_type)s,%(status)s,
                        %(chunk_count)s,%(size_bytes)s,%(created_at)s,%(updated_at)s,%(error)s)
                ON CONFLICT(id) DO UPDATE SET
                  name=EXCLUDED.name,
                  source_type=EXCLUDED.source_type,
                  source_uri=EXCLUDED.source_uri,
                  content_type=EXCLUDED.content_type,
                  status=EXCLUDED.status,
                  chunk_count=EXCLUDED.chunk_count,
                  size_bytes=EXCLUDED.size_bytes,
                  updated_at=EXCLUDED.updated_at,
                  error=EXCLUDED.error
                """,
                data,
            )
        return record

    def get(self, doc_id: str) -> DocumentRecord | None:
        with self.pool.connection() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id=%s", (doc_id,)).fetchone()
        return DocumentRecord(**row) if row else None

    def list(self) -> list[DocumentRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
        return [DocumentRecord(**row) for row in rows]

    def delete(self, doc_id: str) -> bool:
        with self.pool.connection() as conn:
            cur = conn.execute("DELETE FROM documents WHERE id=%s", (doc_id,))
            return cur.rowcount > 0


class PostgresSecurityStore(_PostgresBase):
    def __init__(self, pool: ConnectionPool):
        super().__init__(pool)
        self._init_db()

    def _init_db(self) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS service_keys (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  key_prefix TEXT NOT NULL UNIQUE,
                  key_hash TEXT NOT NULL,
                  scopes JSONB NOT NULL,
                  created_at TIMESTAMPTZ NOT NULL,
                  expires_at TIMESTAMPTZ,
                  revoked_at TIMESTAMPTZ,
                  last_used_at TIMESTAMPTZ,
                  rotated_from TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_service_keys_prefix ON service_keys(key_prefix)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS security_audit (
                  id TEXT PRIMARY KEY,
                  principal_id TEXT,
                  key_prefix TEXT,
                  action TEXT NOT NULL,
                  resource TEXT NOT NULL,
                  outcome TEXT NOT NULL,
                  detail TEXT,
                  created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_security_audit_created ON security_audit(created_at DESC)"
            )

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
        return prefix, raw_key, PostgresSecurityStore._digest(raw_key)

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
        with self.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO service_keys
                (id,name,key_prefix,key_hash,scopes,created_at,expires_at,revoked_at,last_used_at,rotated_from)
                VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s)
                """,
                (
                    key_id,
                    name,
                    prefix,
                    key_hash,
                    json.dumps(normalized_scopes),
                    created_at,
                    expires_at,
                    None,
                    None,
                    rotated_from,
                ),
            )
        return (
            ServiceKeyRecord(
                id=key_id,
                name=name,
                key_prefix=prefix,
                scopes=normalized_scopes,
                created_at=created_at,
                expires_at=expires_at,
                rotated_from=rotated_from,
            ),
            raw_key,
        )

    def verify(self, raw_key: str) -> ServiceKeyRecord | None:
        prefix = self.token_prefix(raw_key)
        if not prefix:
            return None
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM service_keys WHERE key_prefix=%s",
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
                    "UPDATE service_keys SET last_used_at=%s WHERE id=%s",
                    (now, record.id),
                )
                record.last_used_at = now
            return record

    def get_key(self, key_id: str) -> ServiceKeyRecord | None:
        with self.pool.connection() as conn:
            row = conn.execute("SELECT * FROM service_keys WHERE id=%s", (key_id,)).fetchone()
        return self._to_key_record(row) if row else None

    def list_keys(self) -> list[ServiceKeyRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM service_keys ORDER BY created_at DESC"
            ).fetchall()
        return [self._to_key_record(row) for row in rows]

    def revoke(self, key_id: str) -> bool:
        now = self.now()
        with self.pool.connection() as conn:
            cur = conn.execute(
                "UPDATE service_keys SET revoked_at=COALESCE(revoked_at, %s) WHERE id=%s",
                (now, key_id),
            )
            return cur.rowcount > 0

    def rotate(self, key_id: str) -> tuple[ServiceKeyRecord, str] | None:
        new_id = str(uuid4())
        prefix, raw_key, key_hash = self._new_material()
        created_at = self.now()
        with self.pool.connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    "SELECT * FROM service_keys WHERE id=%s FOR UPDATE",
                    (key_id,),
                ).fetchone()
                if not row:
                    return None
                old = self._to_key_record(row)
                if old.revoked_at is not None:
                    return None
                if old.expires_at is not None and old.expires_at <= created_at:
                    return None
                revoked = conn.execute(
                    "UPDATE service_keys SET revoked_at=%s WHERE id=%s AND revoked_at IS NULL",
                    (created_at, old.id),
                )
                if revoked.rowcount != 1:
                    return None
                conn.execute(
                    """
                    INSERT INTO service_keys
                    (id,name,key_prefix,key_hash,scopes,created_at,expires_at,revoked_at,last_used_at,rotated_from)
                    VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s)
                    """,
                    (
                        new_id,
                        old.name,
                        prefix,
                        key_hash,
                        json.dumps(sorted(set(old.scopes))),
                        created_at,
                        old.expires_at,
                        None,
                        None,
                        old.id,
                    ),
                )
        return (
            ServiceKeyRecord(
                id=new_id,
                name=old.name,
                key_prefix=prefix,
                scopes=sorted(set(old.scopes)),
                created_at=created_at,
                expires_at=old.expires_at,
                rotated_from=old.id,
            ),
            raw_key,
        )

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
        with self.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO security_audit
                (id,principal_id,key_prefix,action,resource,outcome,detail,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    record.id,
                    record.principal_id,
                    record.key_prefix,
                    record.action,
                    record.resource,
                    record.outcome,
                    record.detail,
                    record.created_at,
                ),
            )
        return record

    def list_audit(self, limit: int = 100) -> list[AuditRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM security_audit ORDER BY created_at DESC LIMIT %s",
                (limit,),
            ).fetchall()
        return [AuditRecord(**row) for row in rows]

    @staticmethod
    def _to_key_record(row: dict) -> ServiceKeyRecord:
        scopes = row["scopes"]
        if isinstance(scopes, str):
            scopes = json.loads(scopes)
        return ServiceKeyRecord(
            id=row["id"],
            name=row["name"],
            key_prefix=row["key_prefix"],
            scopes=scopes,
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
            last_used_at=row["last_used_at"],
            rotated_from=row["rotated_from"],
        )
