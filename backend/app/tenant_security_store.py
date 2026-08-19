import sqlite3
from datetime import datetime
from typing import Protocol

from psycopg_pool import ConnectionPool

from app.models.schemas import AuditRecord, ServiceKeyRecord


class BaseSecurityStore(Protocol):
    def create_key(
        self,
        name: str,
        scopes: list[str],
        expires_at: datetime | None = None,
        *,
        rotated_from: str | None = None,
    ) -> tuple[ServiceKeyRecord, str]: ...

    def verify(self, raw_key: str) -> ServiceKeyRecord | None: ...
    def get_key(self, key_id: str) -> ServiceKeyRecord | None: ...
    def list_keys(self) -> list[ServiceKeyRecord]: ...
    def revoke(self, key_id: str) -> bool: ...
    def rotate(self, key_id: str) -> tuple[ServiceKeyRecord, str] | None: ...
    def audit(
        self,
        principal_id: str | None,
        key_prefix: str | None,
        action: str,
        resource: str,
        outcome: str,
        detail: str | None = None,
    ) -> AuditRecord: ...
    def list_audit(self, limit: int = 100) -> list[AuditRecord]: ...
    def token_prefix(self, raw_key: str) -> str | None: ...


class TenantSecurityStore:
    """Adds durable tenant ownership to service keys and security audit events.

    Secret digests/scopes and the original audit payload remain in the established
    security store. Tenant ownership is stored in sidecar tables so existing
    SQLite/Postgres installs migrate without rewriting secret material. Legacy keys
    are mapped to the configured default tenant on first observation. Legacy audit
    events remain unscoped and are therefore visible only to bootstrap/global audit.
    """

    def __init__(
        self,
        base: BaseSecurityStore,
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
                    CREATE TABLE IF NOT EXISTS service_key_tenants (
                      key_id TEXT PRIMARY KEY,
                      tenant_id TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS security_audit_tenants (
                      audit_id TEXT PRIMARY KEY,
                      tenant_id TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_security_audit_tenants_tenant "
                    "ON security_audit_tenants(tenant_id, audit_id)"
                )
            return
        assert self.sqlite_path is not None
        with sqlite3.connect(self.sqlite_path, timeout=5.0) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS service_key_tenants (
                  key_id TEXT PRIMARY KEY,
                  tenant_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS security_audit_tenants (
                  audit_id TEXT PRIMARY KEY,
                  tenant_id TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_security_audit_tenants_tenant
                  ON security_audit_tenants(tenant_id, audit_id);
                """
            )
            conn.commit()

    def _mapped_tenant_for(self, key_id: str) -> str | None:
        if self.postgres_pool is not None:
            with self.postgres_pool.connection() as conn:
                row = conn.execute(
                    "SELECT tenant_id FROM service_key_tenants WHERE key_id=%s",
                    (key_id,),
                ).fetchone()
            return str(row["tenant_id"]) if row else None
        assert self.sqlite_path is not None
        with sqlite3.connect(self.sqlite_path, timeout=5.0) as conn:
            row = conn.execute(
                "SELECT tenant_id FROM service_key_tenants WHERE key_id=?",
                (key_id,),
            ).fetchone()
        return str(row[0]) if row else None

    def _tenant_for(self, key_id: str) -> str:
        existing = self._mapped_tenant_for(key_id)
        if existing is not None:
            return existing
        self._bind(key_id, self.default_tenant_id)
        return self.default_tenant_id

    def _bind(self, key_id: str, tenant_id: str) -> None:
        if self.postgres_pool is not None:
            with self.postgres_pool.connection() as conn:
                conn.execute(
                    "INSERT INTO service_key_tenants (key_id,tenant_id) VALUES (%s,%s) "
                    "ON CONFLICT (key_id) DO UPDATE SET tenant_id=EXCLUDED.tenant_id",
                    (key_id, tenant_id),
                )
            return
        assert self.sqlite_path is not None
        with sqlite3.connect(self.sqlite_path, timeout=5.0) as conn:
            conn.execute(
                "INSERT INTO service_key_tenants (key_id,tenant_id) VALUES (?,?) "
                "ON CONFLICT(key_id) DO UPDATE SET tenant_id=excluded.tenant_id",
                (key_id, tenant_id),
            )
            conn.commit()

    def _bind_audit(self, audit_id: str, tenant_id: str) -> None:
        if self.postgres_pool is not None:
            with self.postgres_pool.connection() as conn:
                conn.execute(
                    "INSERT INTO security_audit_tenants (audit_id,tenant_id) VALUES (%s,%s) "
                    "ON CONFLICT (audit_id) DO UPDATE SET tenant_id=EXCLUDED.tenant_id",
                    (audit_id, tenant_id),
                )
            return
        assert self.sqlite_path is not None
        with sqlite3.connect(self.sqlite_path, timeout=5.0) as conn:
            conn.execute(
                "INSERT INTO security_audit_tenants (audit_id,tenant_id) VALUES (?,?) "
                "ON CONFLICT(audit_id) DO UPDATE SET tenant_id=excluded.tenant_id",
                (audit_id, tenant_id),
            )
            conn.commit()

    def _attach(self, record: ServiceKeyRecord | None) -> ServiceKeyRecord | None:
        if record is None:
            return None
        record.tenant_id = self._tenant_for(record.id)
        return record

    def create_key(
        self,
        name: str,
        scopes: list[str],
        expires_at: datetime | None = None,
        *,
        tenant_id: str | None = None,
        rotated_from: str | None = None,
    ) -> tuple[ServiceKeyRecord, str]:
        record, secret = self.base.create_key(
            name,
            scopes,
            expires_at,
            rotated_from=rotated_from,
        )
        self._bind(record.id, tenant_id or self.default_tenant_id)
        attached = self._attach(record)
        assert attached is not None
        return attached, secret

    def verify(self, raw_key: str) -> ServiceKeyRecord | None:
        return self._attach(self.base.verify(raw_key))

    def get_key(self, key_id: str) -> ServiceKeyRecord | None:
        return self._attach(self.base.get_key(key_id))

    def list_keys(self) -> list[ServiceKeyRecord]:
        attached: list[ServiceKeyRecord] = []
        for record in self.base.list_keys():
            item = self._attach(record)
            assert item is not None
            attached.append(item)
        return attached

    def revoke(self, key_id: str) -> bool:
        return self.base.revoke(key_id)

    def rotate(self, key_id: str) -> tuple[ServiceKeyRecord, str] | None:
        old = self.get_key(key_id)
        if old is None:
            return None
        rotated = self.base.rotate(key_id)
        if rotated is None:
            return None
        replacement, secret = rotated
        self._bind(replacement.id, old.tenant_id)
        attached = self._attach(replacement)
        assert attached is not None
        return attached, secret

    def audit(
        self,
        principal_id: str | None,
        key_prefix: str | None,
        action: str,
        resource: str,
        outcome: str,
        detail: str | None = None,
        *,
        tenant_id: str | None = None,
    ) -> AuditRecord:
        effective_tenant = tenant_id
        if effective_tenant is None and principal_id not in {None, "bootstrap"}:
            effective_tenant = self._mapped_tenant_for(principal_id)
        if effective_tenant is None and principal_id == "bootstrap":
            effective_tenant = self.default_tenant_id
        record = self.base.audit(principal_id, key_prefix, action, resource, outcome, detail)
        record.tenant_id = effective_tenant
        if effective_tenant is not None:
            self._bind_audit(record.id, effective_tenant)
        return record

    def list_audit(
        self,
        limit: int = 100,
        *,
        tenant_id: str | None = None,
    ) -> list[AuditRecord]:
        if self.postgres_pool is not None:
            with self.postgres_pool.connection() as conn:
                if tenant_id is None:
                    rows = conn.execute(
                        """
                        SELECT a.*, m.tenant_id
                        FROM security_audit a
                        LEFT JOIN security_audit_tenants m ON m.audit_id=a.id
                        ORDER BY a.created_at DESC LIMIT %s
                        """,
                        (limit,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT a.*, m.tenant_id
                        FROM security_audit a
                        JOIN security_audit_tenants m ON m.audit_id=a.id
                        WHERE m.tenant_id=%s
                        ORDER BY a.created_at DESC LIMIT %s
                        """,
                        (tenant_id, limit),
                    ).fetchall()
            return [AuditRecord(**row) for row in rows]

        assert self.sqlite_path is not None
        with sqlite3.connect(self.sqlite_path, timeout=5.0) as conn:
            conn.row_factory = sqlite3.Row
            if tenant_id is None:
                rows = conn.execute(
                    """
                    SELECT a.*, m.tenant_id
                    FROM security_audit a
                    LEFT JOIN security_audit_tenants m ON m.audit_id=a.id
                    ORDER BY a.created_at DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT a.*, m.tenant_id
                    FROM security_audit a
                    JOIN security_audit_tenants m ON m.audit_id=a.id
                    WHERE m.tenant_id=?
                    ORDER BY a.created_at DESC LIMIT ?
                    """,
                    (tenant_id, limit),
                ).fetchall()
        return [AuditRecord(**dict(row)) for row in rows]

    def token_prefix(self, raw_key: str) -> str | None:
        return self.base.token_prefix(raw_key)
