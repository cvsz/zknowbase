from datetime import timedelta

from app.core.config import Settings
from app.security_store import SecurityStore
from app.tenant_security_store import TenantSecurityStore


def test_service_key_is_hashed_and_revocable(tmp_path):
    settings = Settings(
        api_key="this-is-a-test-secret-key",
        metadata_db=tmp_path / "security.db",
        upload_dir=tmp_path / "uploads",
    )
    settings.ensure_paths()
    store = SecurityStore(settings.metadata_db)

    record, raw_key = store.create_key(
        "zworkforce",
        ["knowledge:read", "knowledge:read"],
    )

    assert raw_key.startswith(f"{record.key_prefix}.")
    assert record.scopes == ["knowledge:read"]
    assert raw_key.encode() not in settings.metadata_db.read_bytes()

    verified = store.verify(raw_key)
    assert verified is not None
    assert verified.id == record.id
    assert verified.last_used_at is not None

    assert store.revoke(record.id) is True
    assert store.verify(raw_key) is None


def test_rotation_revokes_old_key_and_links_replacement(tmp_path):
    settings = Settings(
        api_key="this-is-a-test-secret-key",
        metadata_db=tmp_path / "security.db",
        upload_dir=tmp_path / "uploads",
    )
    settings.ensure_paths()
    store = SecurityStore(settings.metadata_db)

    old, old_secret = store.create_key(
        "zworkforce",
        ["knowledge:read", "knowledge:write"],
        expires_at=store.now() + timedelta(days=30),
    )
    rotated = store.rotate(old.id)
    assert rotated is not None
    replacement, replacement_secret = rotated

    assert replacement.rotated_from == old.id
    assert replacement.scopes == old.scopes
    assert store.verify(old_secret) is None
    assert store.verify(replacement_secret) is not None
    persisted_old = store.get_key(old.id)
    assert persisted_old is not None
    assert persisted_old.revoked_at is not None


def test_expired_key_is_rejected(tmp_path):
    settings = Settings(
        api_key="this-is-a-test-secret-key",
        metadata_db=tmp_path / "security.db",
        upload_dir=tmp_path / "uploads",
    )
    settings.ensure_paths()
    store = SecurityStore(settings.metadata_db)

    _record, raw_key = store.create_key(
        "expired",
        ["knowledge:read"],
        expires_at=store.now() - timedelta(seconds=1),
    )
    assert store.verify(raw_key) is None


def test_audit_records_are_persisted(tmp_path):
    settings = Settings(
        api_key="this-is-a-test-secret-key",
        metadata_db=tmp_path / "security.db",
        upload_dir=tmp_path / "uploads",
    )
    settings.ensure_paths()
    store = SecurityStore(settings.metadata_db)

    event = store.audit(
        "principal-1",
        "zkb_example",
        "service_key.create",
        "key-1",
        "success",
        "test event",
    )
    events = SecurityStore(settings.metadata_db).list_audit()
    assert events[0].id == event.id
    assert events[0].principal_id == "principal-1"
    assert events[0].detail == "test event"


def test_tenant_audit_listing_is_fail_closed(tmp_path):
    db = tmp_path / "tenant-audit.db"
    base = SecurityStore(db)
    store = TenantSecurityStore(base, default_tenant_id="default", sqlite_path=str(db))

    tenant_a, _ = store.create_key("tenant-a", ["audit:read"], tenant_id="tenant-a")
    tenant_b, _ = store.create_key("tenant-b", ["audit:read"], tenant_id="tenant-b")
    event_a = store.audit(
        tenant_a.id,
        tenant_a.key_prefix,
        "query",
        "doc-a",
        "success",
        tenant_id="tenant-a",
    )
    event_b = store.audit(
        tenant_b.id,
        tenant_b.key_prefix,
        "query",
        "doc-b",
        "success",
        tenant_id="tenant-b",
    )
    legacy = base.audit("legacy-principal", "zkb_legacy", "query", "legacy", "success")

    a_events = store.list_audit(100, tenant_id="tenant-a")
    b_events = store.list_audit(100, tenant_id="tenant-b")
    global_events = store.list_audit(100)

    assert [event.id for event in a_events] == [event_a.id]
    assert [event.id for event in b_events] == [event_b.id]
    assert {event.id for event in global_events} >= {event_a.id, event_b.id, legacy.id}
    assert next(event for event in global_events if event.id == legacy.id).tenant_id is None


def test_audit_tenant_can_be_derived_from_service_principal(tmp_path):
    db = tmp_path / "tenant-audit-derived.db"
    store = TenantSecurityStore(
        SecurityStore(db),
        default_tenant_id="default",
        sqlite_path=str(db),
    )
    principal, _ = store.create_key("reader", ["knowledge:read"], tenant_id="acme")

    event = store.audit(
        principal.id,
        principal.key_prefix,
        "authorize",
        "POST /api/v1/query",
        "denied",
    )

    assert event.tenant_id == "acme"
    assert [item.id for item in store.list_audit(10, tenant_id="acme")] == [event.id]
