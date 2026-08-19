from app.security_store import SecurityStore
from app.tenant_security_store import TenantSecurityStore


def test_tenant_binding_persists_and_survives_rotation(tmp_path):
    db_path = tmp_path / "tenant-security.db"
    store = TenantSecurityStore(
        SecurityStore(db_path),
        default_tenant_id="default",
        sqlite_path=str(db_path),
    )
    record, secret = store.create_key(
        "zworkforce-acme",
        ["knowledge:read"],
        tenant_id="acme",
    )
    assert record.tenant_id == "acme"
    assert store.verify(secret).tenant_id == "acme"  # type: ignore[union-attr]

    rotated = store.rotate(record.id)
    assert rotated is not None
    replacement, replacement_secret = rotated
    assert replacement.tenant_id == "acme"
    assert store.verify(secret) is None
    verified = store.verify(replacement_secret)
    assert verified is not None
    assert verified.tenant_id == "acme"


def test_legacy_key_is_mapped_to_default_tenant(tmp_path):
    db_path = tmp_path / "legacy-security.db"
    base = SecurityStore(db_path)
    legacy, secret = base.create_key("legacy", ["knowledge:read"])

    store = TenantSecurityStore(
        SecurityStore(db_path),
        default_tenant_id="default",
        sqlite_path=str(db_path),
    )
    verified = store.verify(secret)
    assert verified is not None
    assert verified.id == legacy.id
    assert verified.tenant_id == "default"

    reopened = TenantSecurityStore(
        SecurityStore(db_path),
        default_tenant_id="other-default",
        sqlite_path=str(db_path),
    )
    persisted = reopened.get_key(legacy.id)
    assert persisted is not None
    assert persisted.tenant_id == "default"
