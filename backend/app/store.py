import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.models.schemas import DocumentRecord


class DocumentStore:
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                  id TEXT PRIMARY KEY,
                  tenant_id TEXT NOT NULL DEFAULT 'default',
                  name TEXT NOT NULL,
                  source_type TEXT NOT NULL,
                  source_uri TEXT,
                  content_type TEXT,
                  content_hash TEXT,
                  status TEXT NOT NULL,
                  chunk_count INTEGER NOT NULL DEFAULT 0,
                  size_bytes INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  error TEXT
                )
                """
            )
            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(documents)").fetchall()
            }
            if "tenant_id" not in columns:
                conn.execute(
                    "ALTER TABLE documents ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'"
                )
            if "content_hash" not in columns:
                conn.execute("ALTER TABLE documents ADD COLUMN content_hash TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_tenant_created "
                "ON documents(tenant_id, created_at DESC)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_tenant_content_hash "
                "ON documents(tenant_id, content_hash) WHERE content_hash IS NOT NULL"
            )
            conn.commit()

    @staticmethod
    def _data(record: DocumentRecord) -> dict:
        data = record.model_dump()
        data["created_at"] = record.created_at.isoformat()
        data["updated_at"] = record.updated_at.isoformat()
        return data

    def upsert(self, record: DocumentRecord) -> DocumentRecord:
        data = self._data(record)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO documents
                (id,tenant_id,name,source_type,source_uri,content_type,content_hash,status,chunk_count,size_bytes,created_at,updated_at,error)
                VALUES (:id,:tenant_id,:name,:source_type,:source_uri,:content_type,:content_hash,:status,:chunk_count,:size_bytes,:created_at,:updated_at,:error)
                ON CONFLICT(id) DO UPDATE SET
                  tenant_id=excluded.tenant_id, name=excluded.name, source_type=excluded.source_type,
                  source_uri=excluded.source_uri, content_type=excluded.content_type,
                  content_hash=excluded.content_hash, status=excluded.status, chunk_count=excluded.chunk_count,
                  size_bytes=excluded.size_bytes, updated_at=excluded.updated_at,
                  error=excluded.error
                """,
                data,
            )
            conn.commit()
        return record

    def insert_if_content_absent(self, record: DocumentRecord) -> tuple[DocumentRecord, bool]:
        """Atomically reserve tenant-scoped content identity for a new document."""
        if record.content_hash is None:
            raise ValueError("content_hash is required for idempotent document insertion")
        data = self._data(record)
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO documents
                (id,tenant_id,name,source_type,source_uri,content_type,content_hash,status,chunk_count,size_bytes,created_at,updated_at,error)
                VALUES (:id,:tenant_id,:name,:source_type,:source_uri,:content_type,:content_hash,:status,:chunk_count,:size_bytes,:created_at,:updated_at,:error)
                ON CONFLICT(tenant_id, content_hash) WHERE content_hash IS NOT NULL DO NOTHING
                """,
                data,
            )
            if cur.rowcount > 0:
                conn.commit()
                return record, True
            row = conn.execute(
                "SELECT * FROM documents WHERE tenant_id=? AND content_hash=?",
                (record.tenant_id, record.content_hash),
            ).fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("content identity reservation conflicted without an existing document")
        return self._to_model(row), False

    def find_by_content_hash(self, tenant_id: str, content_hash: str) -> DocumentRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE tenant_id=? AND content_hash=?",
                (tenant_id, content_hash),
            ).fetchone()
        return self._to_model(row) if row else None

    def get(self, doc_id: str) -> DocumentRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        return self._to_model(row) if row else None

    def list(self) -> list[DocumentRecord]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
        return [self._to_model(row) for row in rows]

    def delete(self, doc_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
            conn.commit()
            return cur.rowcount > 0

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _to_model(row: sqlite3.Row) -> DocumentRecord:
        return DocumentRecord(**dict(row))
