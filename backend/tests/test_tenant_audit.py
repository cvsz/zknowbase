import os
from uuid import uuid4

import pytest

from app.postgres_store import PostgresSecurityStore, create_postgres_pool
from app.security_store import SecurityStore
from app.tenant_security_store import TenantSecurityStore


def _record_tenant_events(store: TenantSecurityStore):
    key_a, _ = store.create_key(
        f"tenant-a-{uuid4().hex[:8]}",
        ["audit:read"],
        tenant_id="tenant-a",
    )
    key_b, _ = store.create_key(
        f"tenant-b-{uuid4().hex[:8]}",
        ["audit:read"],
        tenant_id="tenant-b",
    )
    event_a = store.audit(
        key_a.id,
        key_a.key_prefix,
        "tenant.test",
        "resource-a",
        "success",
    )
    event_b = store.audit(
        key_b.id,
        key_b.key_prefix,
        "tenant.test",
        "resource-b",
        "success",
    )
    return key_a, key_b, event_a, event_b


def test_sqlite_audit_reads_are_tenant_scoped(tmp_path):
    db_path = tmp_path / "audit.db"
    store = TenantSecurityStore(
        SecurityStore(db_path),
        default_tenant_id="default",
        sqlite_path=str(db_path),
    )
    key_a, key_b, event_a, event_b = _record_tenant_events(store)

    tenant_a = store.list_audit(100, tenant_id="tenant-a")
    tenant_b = store.list_audit(100, tenant_id="tenant-b")

    assert event_a.id in {event.id for event in tenant_a}
    assert event_b.id not in {event.id for event in tenant_a}
    assert event_b.id in {event.id for event in tenant_b}
    assert event_a.id not in {event.id for event in tenant_b}
    assert all(event.principal_id != key_b.id for event in tenant_a)
    assert all(event.principal_id != key_a.id for event in tenant_b)


def test_anonymous_audit_events_are_not_attributed_to_a_tenant(tmp_path):
    db_path = tmp_path / "audit.db"
    store = TenantSecurityStore(
        SecurityStore(db_path),
        default_tenant_id="default",
        sqlite_path=str(db_path),
    )
    anonymous = store.audit(
        None,
        None,
        "authenticate",
        "GET /api/v1/audit",
        "denied",
        "missing API key",
    )

    assert anonymous.id not in {
        event.id for event in store.list_audit(100, tenant_id="default")
    }


def test_legacy_key_audit_is_mapped_to_default_tenant(tmp_path):
    db_path = tmp_path / "audit.db"
    base = SecurityStore(db_path)
    legacy_key, _ = base.create_key("legacy", ["audit:read"])
    legacy_event = base.audit(
        legacy_key.id,
        legacy_key.key_prefix,
        "legacy.test",
        "legacy-resource",
        "success",
    )
    store = TenantSecurityStore(
        base,
        default_tenant_id="migration-tenant",
        sqlite_path=str(db_path),
    )

    events = store.list_audit(100, tenant_id="migration-tenant")
    assert legacy_event.id in {event.id for event in events}
    assert legacy_event.id not in {
        event.id for event in store.list_audit(100, tenant_id="other-tenant")
    }


@pytest.mark.skipif(
    not os.getenv("ZKB_TEST_POSTGRES_URL"),
    reason="local Postgres test DSN not configured",
)
def test_postgres_audit_reads_are_tenant_scoped():
    dsn = os.environ["ZKB_TEST_POSTGRES_URL"]
    pool = create_postgres_pool(dsn, min_size=1, max_size=2)
    try:
        store = TenantSecurityStore(
            PostgresSecurityStore(pool),
            default_tenant_id="default",
            postgres_pool=pool,
        )
        _key_a, _key_b, event_a, event_b = _record_tenant_events(store)
        tenant_a_ids = {
            event.id for event in store.list_audit(100, tenant_id="tenant-a")
        }
        tenant_b_ids = {
            event.id for event in store.list_audit(100, tenant_id="tenant-b")
        }
        assert event_a.id in tenant_a_ids
        assert event_b.id not in tenant_a_ids
        assert event_b.id in tenant_b_ids
        assert event_a.id not in tenant_b_ids
    finally:
        pool.close()
