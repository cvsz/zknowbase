import sqlite3
from typing import Protocol

from psycopg_pool import ConnectionPool

from app.models.schemas import IngestionJobRecord


class BaseIngestionQueue(Protocol):
    def enqueue(
        self,
        document_id: str,
        source_type: str,
        source_uri: str,
        max_attempts: int = 3,
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

    The existing queue implementation retains lease/retry/concurrency semantics. Tenant
    ownership lives in a companion table so existing SQLite/Postgres queues can migrate
    without rewriting active jobs. Legacy jobs are deterministically assigned to the
    configured default tenant when first observed.
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
            conn.commit()

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
        tenant_id: str,
        document_id: str,
        source_type: str,
        source_uri: str,
        max_attempts: int = 3,
    ) -> IngestionJobRecord:
        job = self.base.enqueue(document_id, source_type, source_uri, max_attempts)
        self._bind(job.id, tenant_id)
        job.tenant_id = tenant_id
        return job

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
        return any(
            job.document_id == document_id and job.status in {"queued", "processing"}
            for job in self.list(500, tenant_id)
        )

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
