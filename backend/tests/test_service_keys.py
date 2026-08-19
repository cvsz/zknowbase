from datetime import timedelta

from app.core.config import Settings
from app.security_store import SecurityStore


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
