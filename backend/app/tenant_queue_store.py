from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from psycopg_pool import ConnectionPool

from app.models.schemas import IngestionJobRecord


class ActiveIngestionJobError(RuntimeError):
    """Raised when an atomic enqueue observes an existing active job."""


class BaseIngestionQueue(Protocol):
    def enqueue(
        self,
        document_id: str,
        source_type: str,
        source_uri: str,
        max_attempts: int = 3,
        available_at: datetime | None = None,
    ) -> IngestionJobRecord: ...

    def get(self, job_id: str) -> IngestionJobRecord | None: ...
    def list(self, limit: int = 100) -> list[IngestionJobRecord]: ...
    def active_for_document(self, document_id: str) -> bool: ...
    def reap_expired(self) -> list[IngestionJobRecord]: ...
    def claim_next(self, worker_id: str, lease_seconds: int = 300) -> IngestionJobRecord | None: ...
    def renew(self, job_id: str, worker_id: str, lease_seconds: int) -> bool: ...
    def complete(self, job_id: str, worker_id: str) -> bool: ...
    def fail(self, job_id: str, worker_id: str, error: str) -> bool: ...
    def cancel(self, job_id: str) -> bool: ...


class TenantIngestionQueue:
    """Durably binds ingestion jobs to a server-authoritative tenant.

    Tenant ownership is stored beside the existing queue rows. New jobs are inserted
    together with their tenant binding in one database transaction so an authenticated
    enqueue can never leave behind a durable unowned job. Legacy rows that predate the
    tenant table retain the documented deterministic default-tenant migration behavior.
    """

    def __init__(
        self,
        base: BaseIngestionQueue,
        *,
        default_tenant_id: str,
        sqlite_path: str | None = None,
        postgres_pool: ConnectionPool | None = None,
    ):
        if (sqlite_path is None) == (postgres_pool is None):
            raise ValueError("exactly one tenant mapping backend is required")
        self.base = base
        self.default_tenant_id = default_tenant_id
        self.sqlite_path = sqlite_path
        self.postgres_pool = postgres_pool
        self._init_db()

    def _init_db(self) -> None:
        if self.postgres_pool is not None:
            with self.postgres_pool.connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ingestion_job_tenants (
                      job_id TEXT PRIMARY KEY,
                      tenant_id TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_ingestion_job_tenants_tenant "
                    "ON ingestion_job_tenants(tenant_id)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ingestion_job_reindex_state (
                      job_id TEXT PRIMARY KEY,
                      prior_status TEXT NOT NULL,
                      prior_error TEXT,
                      prior_updated_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
            return
        assert self.sqlite_path is not None
        with sqlite3.connect(self.sqlite_path, timeout=5.0) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_job_tenants (
                  job_id TEXT PRIMARY KEY,
                  tenant_id TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ingestion_job_tenants_tenant "
                "ON ingestion_job_tenants(tenant_id)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_job_reindex_state (
                  job_id TEXT PRIMARY KEY,
                  prior_status TEXT NOT NULL,
                  prior_error TEXT,
                  prior_updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    @staticmethod
    def _new_record(
        job_id: str,
        document_id: str,
        source_type: str,
        source_uri: str,
        max_attempts: int,
        available_at: datetime | None,
        tenant_id: str,
    ) -> IngestionJobRecord:
        now = datetime.now(timezone.utc)
        return IngestionJobRecord(
            id=job_id,
            document_id=document_id,
            tenant_id=tenant_id,
            source_type=source_type,
            source_uri=source_uri,
            status="queued",
            attempts=0,
            max_attempts=max_attempts,
            available_at=available_at,
            created_at=now,
            updated_at=now,
        )

    def _enqueue_bound(
        self,
        document_id: str,
        source_type: str,
        source_uri: str,
        max_attempts: int,
        available_at: datetime | None,
        tenant_id: str,
        *,
        require_inactive: bool,
        prior_status: str | None = None,
        prior_error: str | None = None,
        prior_updated_at: datetime | None = None,
    ) -> IngestionJobRecord:
        job_id = str(uuid4())
        record = self._new_record(
            job_id,
            document_id,
            source_type,
            source_uri,
            max_attempts,
            available_at,
            tenant_id,
        )
        if self.postgres_pool is not None:
            with self.postgres_pool.connection() as conn:
                with conn.transaction():
                    if require_inactive:
                        conn.execute(
                            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                            (f"{tenant_id}\0{document_id}",),
                        )
                        active = conn.execute(
                            """
                            SELECT 1
                            FROM ingestion_jobs AS j
                            JOIN ingestion_job_tenants AS t ON t.job_id=j.id
                            WHERE j.document_id=%s AND t.tenant_id=%s
                              AND j.status IN ('queued','processing')
                            LIMIT 1
                            """,
                            (document_id, tenant_id),
                        ).fetchone()
                        if active:
                            raise ActiveIngestionJobError("Document has an active ingestion job")
                    conn.execute(
                        "INSERT INTO ingestion_job_tenants (job_id,tenant_id) VALUES (%s,%s)",
                        (job_id, tenant_id),
                    )
                    conn.execute(
                        """
                        INSERT INTO ingestion_jobs
                        (id,document_id,source_type,source_uri,status,attempts,max_attempts,
                         worker_id,lease_expires_at,available_at,created_at,updated_at,error)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            job_id,
                            document_id,
                            source_type,
                            source_uri,
                            "queued",
                            0,
                            max_attempts,
                            None,
                            None,
                            available_at,
                            record.created_at,
                            record.updated_at,
                            None,
                        ),
                    )
                    if prior_status is not None and prior_updated_at is not None:
                        conn.execute(
                            """
                            INSERT INTO ingestion_job_reindex_state
                            (job_id,prior_status,prior_error,prior_updated_at)
                            VALUES (%s,%s,%s,%s)
                            """,
                            (job_id, prior_status, prior_error, prior_updated_at),
                        )
            return record

        assert self.sqlite_path is not None
        with sqlite3.connect(self.sqlite_path, timeout=5.0) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if require_inactive:
                    active = conn.execute(
                        """
                        SELECT 1
                        FROM ingestion_jobs AS j
                        JOIN ingestion_job_tenants AS t ON t.job_id=j.id
                        WHERE j.document_id=? AND t.tenant_id=?
                          AND j.status IN ('queued','processing')
                        LIMIT 1
                        """,
                        (document_id, tenant_id),
                    ).fetchone()
                    if active:
                        raise ActiveIngestionJobError("Document has an active ingestion job")
                conn.execute(
                    "INSERT INTO ingestion_job_tenants (job_id,tenant_id) VALUES (?,?)",
                    (job_id, tenant_id),
                )
                conn.execute(
                    """
                    INSERT INTO ingestion_jobs
                    (id,document_id,source_type,source_uri,status,attempts,max_attempts,
                     worker_id,lease_expires_at,available_at,created_at,updated_at,error)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        job_id,
                        document_id,
                        source_type,
                        source_uri,
                        "queued",
                        0,
                        max_attempts,
                        None,
                        None,
                        available_at.isoformat() if available_at is not None else None,
                        record.created_at.isoformat(),
                        record.updated_at.isoformat(),
                        None,
                    ),
                )
                if prior_status is not None and prior_updated_at is not None:
                    conn.execute(
                        """
                        INSERT INTO ingestion_job_reindex_state
                        (job_id,prior_status,prior_error,prior_updated_at)
                        VALUES (?,?,?,?)
                        """,
                        (job_id, prior_status, prior_error, prior_updated_at.isoformat()),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return record

    def _bind(self, job_id: str, tenant_id: str) -> None:
        if self.postgres_pool is not None:
            with self.postgres_pool.connection() as conn:
                conn.execute(
                    "INSERT INTO ingestion_job_tenants (job_id,tenant_id) VALUES (%s,%s) "
                    "ON CONFLICT (job_id) DO UPDATE SET tenant_id=EXCLUDED.tenant_id",
                    (job_id, tenant_id),
                )
            return
        assert self.sqlite_path is not None
        with sqlite3.connect(self.sqlite_path, timeout=5.0) as conn:
            conn.execute(
                "INSERT INTO ingestion_job_tenants (job_id,tenant_id) VALUES (?,?) "
                "ON CONFLICT(job_id) DO UPDATE SET tenant_id=excluded.tenant_id",
                (job_id, tenant_id),
            )
            conn.commit()

    def _tenant_for(self, job_id: str) -> str:
        if self.postgres_pool is not None:
            with self.postgres_pool.connection() as conn:
                row = conn.execute(
                    "SELECT tenant_id FROM ingestion_job_tenants WHERE job_id=%s",
                    (job_id,),
                ).fetchone()
                if row:
                    return str(row["tenant_id"])
                conn.execute(
                    "INSERT INTO ingestion_job_tenants (job_id,tenant_id) VALUES (%s,%s) "
                    "ON CONFLICT (job_id) DO NOTHING",
                    (job_id, self.default_tenant_id),
                )
            return self.default_tenant_id
        assert self.sqlite_path is not None
        with sqlite3.connect(self.sqlite_path, timeout=5.0) as conn:
            row = conn.execute(
                "SELECT tenant_id FROM ingestion_job_tenants WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if row:
                return str(row[0])
            conn.execute(
                "INSERT OR IGNORE INTO ingestion_job_tenants (job_id,tenant_id) VALUES (?,?)",
                (job_id, self.default_tenant_id),
            )
            conn.commit()
        return self.default_tenant_id

    def _attach(self, job: IngestionJobRecord | None) -> IngestionJobRecord | None:
        if job is None:
            return None
        job.tenant_id = self._tenant_for(job.id)
        return job

    def enqueue(
        self,
        document_id: str,
        source_type: str,
        source_uri: str,
        max_attempts: int = 3,
        available_at: datetime | None = None,
        *,
        tenant_id: str | None = None,
    ) -> IngestionJobRecord:
        effective_tenant = tenant_id or self.default_tenant_id
        return self._enqueue_bound(
            document_id,
            source_type,
            source_uri,
            max_attempts,
            available_at,
            effective_tenant,
            require_inactive=False,
        )

    def enqueue_if_inactive(
        self,
        document_id: str,
        source_type: str,
        source_uri: str,
        max_attempts: int = 3,
        available_at: datetime | None = None,
        *,
        tenant_id: str | None = None,
        prior_status: str | None = None,
        prior_error: str | None = None,
        prior_updated_at: datetime | None = None,
    ) -> IngestionJobRecord:
        effective_tenant = tenant_id or self.default_tenant_id
        return self._enqueue_bound(
            document_id,
            source_type,
            source_uri,
            max_attempts,
            available_at,
            effective_tenant,
            require_inactive=True,
            prior_status=prior_status,
            prior_error=prior_error,
            prior_updated_at=prior_updated_at,
        )

    def get(self, job_id: str, tenant_id: str | None = None) -> IngestionJobRecord | None:
        job = self._attach(self.base.get(job_id))
        if job is None or (tenant_id is not None and job.tenant_id != tenant_id):
            return None
        return job

    def list(self, limit: int = 100, tenant_id: str | None = None) -> list[IngestionJobRecord]:
        jobs = [self._attach(job) for job in self.base.list(limit)]
        attached = [job for job in jobs if job is not None]
        if tenant_id is None:
            return attached
        return [job for job in attached if job.tenant_id == tenant_id]

    def active_for_document(self, document_id: str, tenant_id: str | None = None) -> bool:
        if tenant_id is None:
            return self.base.active_for_document(document_id)
        if self.postgres_pool is not None:
            with self.postgres_pool.connection() as conn:
                row = conn.execute(
                    """
                    SELECT 1
                    FROM ingestion_jobs AS j
                    JOIN ingestion_job_tenants AS t ON t.job_id=j.id
                    WHERE j.document_id=%s AND t.tenant_id=%s
                      AND j.status IN ('queued','processing')
                    LIMIT 1
                    """,
                    (document_id, tenant_id),
                ).fetchone()
            return row is not None
        assert self.sqlite_path is not None
        with sqlite3.connect(self.sqlite_path, timeout=5.0) as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM ingestion_jobs AS j
                JOIN ingestion_job_tenants AS t ON t.job_id=j.id
                WHERE j.document_id=? AND t.tenant_id=?
                  AND j.status IN ('queued','processing')
                LIMIT 1
                """,
                (document_id, tenant_id),
            ).fetchone()
        return row is not None

    def reindex_prior_state(
        self,
        job_id: str,
        tenant_id: str | None = None,
    ) -> tuple[str, str | None, datetime] | None:
        if tenant_id is not None and self.get(job_id, tenant_id) is None:
            return None
        if self.postgres_pool is not None:
            with self.postgres_pool.connection() as conn:
                row = conn.execute(
                    """
                    SELECT prior_status,prior_error,prior_updated_at
                    FROM ingestion_job_reindex_state WHERE job_id=%s
                    """,
                    (job_id,),
                ).fetchone()
            if not row:
                return None
            return str(row["prior_status"]), row["prior_error"], row["prior_updated_at"]
        assert self.sqlite_path is not None
        with sqlite3.connect(self.sqlite_path, timeout=5.0) as conn:
            row = conn.execute(
                """
                SELECT prior_status,prior_error,prior_updated_at
                FROM ingestion_job_reindex_state WHERE job_id=?
                """,
                (job_id,),
            ).fetchone()
        if not row:
            return None
        return str(row[0]), row[1], datetime.fromisoformat(str(row[2]))

    def clear_reindex_state(self, job_id: str) -> None:
        if self.postgres_pool is not None:
            with self.postgres_pool.connection() as conn:
                conn.execute("DELETE FROM ingestion_job_reindex_state WHERE job_id=%s", (job_id,))
            return
        assert self.sqlite_path is not None
        with sqlite3.connect(self.sqlite_path, timeout=5.0) as conn:
            conn.execute("DELETE FROM ingestion_job_reindex_state WHERE job_id=?", (job_id,))
            conn.commit()

    def reap_expired(self) -> list[IngestionJobRecord]:
        return [job for job in (self._attach(item) for item in self.base.reap_expired()) if job is not None]

    def claim_next(self, worker_id: str, lease_seconds: int = 300) -> IngestionJobRecord | None:
        return self._attach(self.base.claim_next(worker_id, lease_seconds))

    def renew(self, job_id: str, worker_id: str, lease_seconds: int) -> bool:
        return self.base.renew(job_id, worker_id, lease_seconds)

    def complete(self, job_id: str, worker_id: str) -> bool:
        return self.base.complete(job_id, worker_id)

    def fail(self, job_id: str, worker_id: str, error: str) -> bool:
        return self.base.fail(job_id, worker_id, error)

    def cancel(self, job_id: str, tenant_id: str | None = None) -> bool:
        if tenant_id is not None and self.get(job_id, tenant_id) is None:
            return False
        return self.base.cancel(job_id)
