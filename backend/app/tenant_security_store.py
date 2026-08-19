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
    """Adds durable tenant ownership to existing service-key stores.

    The key digest/scopes lifecycle stays in the established security store. Tenant
    ownership is kept in a separate keyed table so existing SQLite/Postgres installs
    can migrate without rewriting secret material or invalidating active keys.
    Existing keys are mapped to the configured default tenant on first observation.
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
                    "CREATE INDEX IF NOT EXISTS idx_service_key_tenants_tenant ON service_key_tenants(tenant_id)"
                )
            return
        assert self.sqlite_path is not None
        with sqlite3.connect(self.sqlite_path, timeout=5.0) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS service_key_tenants (
                  key_id TEXT PRIMARY KEY,
                  tenant_id TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_service_key_tenants_tenant ON service_key_tenants(tenant_id)"
            )
            conn.commit()

    def _tenant_for(self, key_id: str) -> str:
        if self.postgres_pool is not None:
            with self.postgres_pool.connection() as conn:
                row = conn.execute(
                    "SELECT tenant_id FROM service_key_tenants WHERE key_id=%s",
                    (key_id,),
                ).fetchone()
                if row:
                    return str(row["tenant_id"])
                conn.execute(
                    "INSERT INTO service_key_tenants (key_id,tenant_id) VALUES (%s,%s) ON CONFLICT (key_id) DO NOTHING",
                    (key_id, self.default_tenant_id),
                )
            return self.default_tenant_id
        assert self.sqlite_path is not None
        with sqlite3.connect(self.sqlite_path, timeout=5.0) as conn:
            row = conn.execute(
                "SELECT tenant_id FROM service_key_tenants WHERE key_id=?",
                (key_id,),
            ).fetchone()
            if row:
                return str(row[0])
            conn.execute(
                "INSERT OR IGNORE INTO service_key_tenants (key_id,tenant_id) VALUES (?,?)",
                (key_id, self.default_tenant_id),
            )
            conn.commit()
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

    def _attach(self, record: ServiceKeyRecord | None) -> ServiceKeyRecord | None:
        if record is None:
            return None
        record.tenant_id = self._tenant_for(record.id)
        return record

    def _backfill_legacy_key_tenants(self) -> None:
        """Map pre-tenant service keys to the configured migration tenant."""
        for record in self.base.list_keys():
            self._tenant_for(record.id)

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
        return self._attach(record), secret  # type: ignore[return-value]

    def verify(self, raw_key: str) -> ServiceKeyRecord | None:
        return self._attach(self.base.verify(raw_key))

    def get_key(self, key_id: str) -> ServiceKeyRecord | None:
        return self._attach(self.base.get_key(key_id))

    def list_keys(self) -> list[ServiceKeyRecord]:
        return [self._attach(record) for record in self.base.list_keys()]  # type: ignore[misc]

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
    ) -> AuditRecord:
        return self.base.audit(principal_id, key_prefix, action, resource, outcome, detail)

    def list_audit(self, limit: int = 100, *, tenant_id: str | None = None) -> list[AuditRecord]:
        """Return audit events, optionally constrained to one authoritative tenant.

        Tenant-scoped reads join audit principals to durable service-key ownership.
        Anonymous/unknown-key authentication failures are deliberately excluded from
        tenant views because they have no trustworthy tenant identity. Legacy service
        keys are first mapped to the configured default tenant for deterministic
        migration. The unscoped mode is retained only for internal compatibility and
        must not be exposed by tenant-facing APIs.
        """
        if tenant_id is None:
            return self.base.list_audit(limit)
        self._backfill_legacy_key_tenants()
        if self.postgres_pool is not None:
            with self.postgres_pool.connection() as conn:
                rows = conn.execute(
                    """
                    SELECT a.*
                    FROM security_audit AS a
                    LEFT JOIN service_key_tenants AS t ON t.key_id = a.principal_id
                    WHERE t.tenant_id = %s
                       OR (a.principal_id = 'bootstrap' AND %s = %s)
                    ORDER BY a.created_at DESC
                    LIMIT %s
                    """,
                    (tenant_id, tenant_id, self.default_tenant_id, limit),
                ).fetchall()
            return [AuditRecord(**row) for row in rows]
        assert self.sqlite_path is not None
        with sqlite3.connect(self.sqlite_path, timeout=5.0) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT a.*
                FROM security_audit AS a
                LEFT JOIN service_key_tenants AS t ON t.key_id = a.principal_id
                WHERE t.tenant_id = ?
                   OR (a.principal_id = 'bootstrap' AND ? = ?)
                ORDER BY a.created_at DESC
                LIMIT ?
                """,
                (tenant_id, tenant_id, self.default_tenant_id, limit),
            ).fetchall()
        return [AuditRecord(**dict(row)) for row in rows]

    def token_prefix(self, raw_key: str) -> str | None:
        return self.base.token_prefix(raw_key)