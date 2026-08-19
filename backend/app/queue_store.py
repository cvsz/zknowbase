import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from psycopg_pool import ConnectionPool

from app.models.schemas import IngestionJobRecord


class SQLiteIngestionQueue:
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
                CREATE TABLE IF NOT EXISTS ingestion_jobs (
                  id TEXT PRIMARY KEY,
                  document_id TEXT NOT NULL,
                  source_type TEXT NOT NULL,
                  source_uri TEXT NOT NULL,
                  status TEXT NOT NULL,
                  attempts INTEGER NOT NULL DEFAULT 0,
                  max_attempts INTEGER NOT NULL DEFAULT 3,
                  worker_id TEXT,
                  lease_expires_at TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  error TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status_created "
                "ON ingestion_jobs(status, created_at)"
            )
            conn.commit()

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    def enqueue(self, document_id: str, source_type: str, source_uri: str, max_attempts: int = 3) -> IngestionJobRecord:
        now = self.now()
        record = IngestionJobRecord(
            id=str(uuid4()), document_id=document_id, source_type=source_type,
            source_uri=source_uri, status="queued", attempts=0,
            max_attempts=max_attempts, created_at=now, updated_at=now,
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ingestion_jobs
                (id,document_id,source_type,source_uri,status,attempts,max_attempts,
                 worker_id,lease_expires_at,created_at,updated_at,error)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (record.id, document_id, source_type, source_uri, "queued", 0,
                 max_attempts, None, None, now.isoformat(), now.isoformat(), None),
            )
            conn.commit()
        return record

    def get(self, job_id: str) -> IngestionJobRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM ingestion_jobs WHERE id=?", (job_id,)).fetchone()
        return self._to_model(row) if row else None

    def list(self, limit: int = 100) -> list[IngestionJobRecord]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM ingestion_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._to_model(row) for row in rows]

    def claim_next(self, worker_id: str, lease_seconds: int = 300) -> IngestionJobRecord | None:
        now = self.now()
        lease = now + timedelta(seconds=lease_seconds)
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE ingestion_jobs
                SET status='failed', worker_id=NULL, lease_expires_at=NULL, updated_at=?,
                    error=COALESCE(error, 'job lease expired')
                WHERE status='processing' AND lease_expires_at IS NOT NULL
                  AND lease_expires_at < ? AND attempts >= max_attempts
                """,
                (now.isoformat(), now.isoformat()),
            )
            conn.execute(
                """
                UPDATE ingestion_jobs
                SET status='queued', worker_id=NULL, lease_expires_at=NULL, updated_at=?
                WHERE status='processing' AND lease_expires_at IS NOT NULL
                  AND lease_expires_at < ? AND attempts < max_attempts
                """,
                (now.isoformat(), now.isoformat()),
            )
            row = conn.execute(
                """SELECT * FROM ingestion_jobs
                   WHERE status='queued' AND attempts < max_attempts
                   ORDER BY created_at ASC LIMIT 1"""
            ).fetchone()
            if not row:
                conn.commit()
                return None
            cur = conn.execute(
                """
                UPDATE ingestion_jobs
                SET status='processing', attempts=attempts+1, worker_id=?,
                    lease_expires_at=?, updated_at=?, error=NULL
                WHERE id=? AND status='queued'
                """,
                (worker_id, lease.isoformat(), now.isoformat(), row["id"]),
            )
            if cur.rowcount != 1:
                conn.rollback()
                return None
            claimed = conn.execute("SELECT * FROM ingestion_jobs WHERE id=?", (row["id"],)).fetchone()
            conn.commit()
        return self._to_model(claimed)

    def renew(self, job_id: str, worker_id: str, lease_seconds: int) -> bool:
        now = self.now()
        lease = now + timedelta(seconds=lease_seconds)
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """UPDATE ingestion_jobs SET lease_expires_at=?, updated_at=?
                   WHERE id=? AND status='processing' AND worker_id=?""",
                (lease.isoformat(), now.isoformat(), job_id, worker_id),
            )
            conn.commit()
            return cur.rowcount == 1

    def complete(self, job_id: str, worker_id: str) -> bool:
        now = self.now().isoformat()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """UPDATE ingestion_jobs
                   SET status='completed', worker_id=NULL, lease_expires_at=NULL,
                       updated_at=?, error=NULL
                   WHERE id=? AND status='processing' AND worker_id=?""",
                (now, job_id, worker_id),
            )
            conn.commit()
            return cur.rowcount == 1

    def fail(self, job_id: str, worker_id: str, error: str) -> bool:
        now = self.now().isoformat()
        bounded_error = error[:4000]
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT attempts,max_attempts FROM ingestion_jobs WHERE id=? AND status='processing' AND worker_id=?",
                (job_id, worker_id),
            ).fetchone()
            if not row:
                return False
            next_status = "queued" if row["attempts"] < row["max_attempts"] else "failed"
            cur = conn.execute(
                """UPDATE ingestion_jobs
                   SET status=?, worker_id=NULL, lease_expires_at=NULL, updated_at=?, error=?
                   WHERE id=? AND status='processing' AND worker_id=?""",
                (next_status, now, bounded_error, job_id, worker_id),
            )
            conn.commit()
            return cur.rowcount == 1

    def cancel(self, job_id: str) -> bool:
        now = self.now().isoformat()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """UPDATE ingestion_jobs
                   SET status='cancelled', worker_id=NULL, lease_expires_at=NULL, updated_at=?
                   WHERE id=? AND status='queued'""",
                (now, job_id),
            )
            conn.commit()
            return cur.rowcount == 1

    @staticmethod
    def _to_model(row: sqlite3.Row) -> IngestionJobRecord:
        return IngestionJobRecord(**dict(row))


class PostgresIngestionQueue:
    def __init__(self, pool: ConnectionPool):
        self.pool = pool
        self._init_db()

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    def _init_db(self) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_jobs (
                  id TEXT PRIMARY KEY,
                  document_id TEXT NOT NULL,
                  source_type TEXT NOT NULL,
                  source_uri TEXT NOT NULL,
                  status TEXT NOT NULL,
                  attempts INTEGER NOT NULL DEFAULT 0,
                  max_attempts INTEGER NOT NULL DEFAULT 3,
                  worker_id TEXT,
                  lease_expires_at TIMESTAMPTZ,
                  created_at TIMESTAMPTZ NOT NULL,
                  updated_at TIMESTAMPTZ NOT NULL,
                  error TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status_created ON ingestion_jobs(status, created_at)"
            )

    def enqueue(self, document_id: str, source_type: str, source_uri: str, max_attempts: int = 3) -> IngestionJobRecord:
        now = self.now()
        record = IngestionJobRecord(
            id=str(uuid4()), document_id=document_id, source_type=source_type,
            source_uri=source_uri, status="queued", attempts=0,
            max_attempts=max_attempts, created_at=now, updated_at=now,
        )
        with self.pool.connection() as conn:
            conn.execute(
                """INSERT INTO ingestion_jobs
                   (id,document_id,source_type,source_uri,status,attempts,max_attempts,
                    worker_id,lease_expires_at,created_at,updated_at,error)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (record.id, document_id, source_type, source_uri, "queued", 0,
                 max_attempts, None, None, now, now, None),
            )
        return record

    def get(self, job_id: str) -> IngestionJobRecord | None:
        with self.pool.connection() as conn:
            row = conn.execute("SELECT * FROM ingestion_jobs WHERE id=%s", (job_id,)).fetchone()
        return IngestionJobRecord(**row) if row else None

    def list(self, limit: int = 100) -> list[IngestionJobRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM ingestion_jobs ORDER BY created_at DESC LIMIT %s", (limit,)
            ).fetchall()
        return [IngestionJobRecord(**row) for row in rows]

    def claim_next(self, worker_id: str, lease_seconds: int = 300) -> IngestionJobRecord | None:
        now = self.now()
        lease = now + timedelta(seconds=lease_seconds)
        with self.pool.connection() as conn:
            with conn.transaction():
                conn.execute(
                    """UPDATE ingestion_jobs
                       SET status='failed', worker_id=NULL, lease_expires_at=NULL, updated_at=%s,
                           error=COALESCE(error, 'job lease expired')
                       WHERE status='processing' AND lease_expires_at IS NOT NULL
                         AND lease_expires_at < %s AND attempts >= max_attempts""",
                    (now, now),
                )
                conn.execute(
                    """UPDATE ingestion_jobs
                       SET status='queued', worker_id=NULL, lease_expires_at=NULL, updated_at=%s
                       WHERE status='processing' AND lease_expires_at IS NOT NULL
                         AND lease_expires_at < %s AND attempts < max_attempts""",
                    (now, now),
                )
                row = conn.execute(
                    """SELECT * FROM ingestion_jobs
                       WHERE status='queued' AND attempts < max_attempts
                       ORDER BY created_at ASC FOR UPDATE SKIP LOCKED LIMIT 1"""
                ).fetchone()
                if not row:
                    return None
                claimed = conn.execute(
                    """UPDATE ingestion_jobs
                       SET status='processing', attempts=attempts+1, worker_id=%s,
                           lease_expires_at=%s, updated_at=%s, error=NULL
                       WHERE id=%s AND status='queued' RETURNING *""",
                    (worker_id, lease, now, row["id"]),
                ).fetchone()
                return IngestionJobRecord(**claimed) if claimed else None

    def renew(self, job_id: str, worker_id: str, lease_seconds: int) -> bool:
        now = self.now()
        lease = now + timedelta(seconds=lease_seconds)
        with self.pool.connection() as conn:
            cur = conn.execute(
                """UPDATE ingestion_jobs SET lease_expires_at=%s, updated_at=%s
                   WHERE id=%s AND status='processing' AND worker_id=%s""",
                (lease, now, job_id, worker_id),
            )
            return cur.rowcount == 1

    def complete(self, job_id: str, worker_id: str) -> bool:
        now = self.now()
        with self.pool.connection() as conn:
            cur = conn.execute(
                """UPDATE ingestion_jobs
                   SET status='completed', worker_id=NULL, lease_expires_at=NULL,
                       updated_at=%s, error=NULL
                   WHERE id=%s AND status='processing' AND worker_id=%s""",
                (now, job_id, worker_id),
            )
            return cur.rowcount == 1

    def fail(self, job_id: str, worker_id: str, error: str) -> bool:
        now = self.now()
        bounded_error = error[:4000]
        with self.pool.connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    """SELECT attempts,max_attempts FROM ingestion_jobs
                       WHERE id=%s AND status='processing' AND worker_id=%s FOR UPDATE""",
                    (job_id, worker_id),
                ).fetchone()
                if not row:
                    return False
                next_status = "queued" if row["attempts"] < row["max_attempts"] else "failed"
                cur = conn.execute(
                    """UPDATE ingestion_jobs
                       SET status=%s, worker_id=NULL, lease_expires_at=NULL, updated_at=%s, error=%s
                       WHERE id=%s AND status='processing' AND worker_id=%s""",
                    (next_status, now, bounded_error, job_id, worker_id),
                )
                return cur.rowcount == 1

    def cancel(self, job_id: str) -> bool:
        now = self.now()
        with self.pool.connection() as conn:
            cur = conn.execute(
                """UPDATE ingestion_jobs
                   SET status='cancelled', worker_id=NULL, lease_expires_at=NULL, updated_at=%s
                   WHERE id=%s AND status='queued'""",
                (now, job_id),
            )
            return cur.rowcount == 1
