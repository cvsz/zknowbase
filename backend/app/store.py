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
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
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
                  size_bytes INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  error TEXT
                )
                """
            )
            conn.commit()

    def upsert(self, record: DocumentRecord) -> DocumentRecord:
        data = record.model_dump()
        data["created_at"] = record.created_at.isoformat()
        data["updated_at"] = record.updated_at.isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO documents
                (id,name,source_type,source_uri,content_type,status,chunk_count,size_bytes,created_at,updated_at,error)
                VALUES (:id,:name,:source_type,:source_uri,:content_type,:status,:chunk_count,:size_bytes,:created_at,:updated_at,:error)
                ON CONFLICT(id) DO UPDATE SET
                  name=excluded.name, source_type=excluded.source_type,
                  source_uri=excluded.source_uri, content_type=excluded.content_type,
                  status=excluded.status, chunk_count=excluded.chunk_count,
                  size_bytes=excluded.size_bytes, updated_at=excluded.updated_at,
                  error=excluded.error
                """,
                data,
            )
            conn.commit()
        return record

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
