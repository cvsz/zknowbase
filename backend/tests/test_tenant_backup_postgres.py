import json
import os
from uuid import uuid4

import pytest

import app.backup as backup
from app.core.config import Settings
from app.postgres_store import PostgresSecurityStore, create_postgres_pool
from app.queue_store import PostgresIngestionQueue
from app.tenant_queue_store import TenantIngestionQueue
from app.tenant_security_store import TenantSecurityStore

POSTGRES_URL = os.getenv("ZKB_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="local Postgres test DSN not configured")


def test_postgres_backup_preserves_tenant_mapping_tables(tmp_path):
    assert POSTGRES_URL is not None
    pool = create_postgres_pool(POSTGRES_URL, min_size=1, max_size=3)
    tenant_id = f"tenant-{uuid4().hex[:8]}"
    security = TenantSecurityStore(
        PostgresSecurityStore(pool),
        default_tenant_id="default",
        postgres_pool=pool,
    )
    queue = TenantIngestionQueue(
        PostgresIngestionQueue(pool),
        default_tenant_id="default",
        postgres_pool=pool,
    )
    key = None
    job = None
    try:
        key, _secret = security.create_key(
            f"backup-{uuid4().hex[:8]}",
            ["knowledge:read"],
            tenant_id=tenant_id,
        )
        job = queue.enqueue(
            f"doc-{uuid4().hex[:8]}",
            "url",
            "https://example.invalid/policy",
            tenant_id=tenant_id,
        )
        settings = Settings(
            api_key="this-is-a-test-secret-key",
            metadata_backend="postgres",
            postgres_url=POSTGRES_URL,
            metadata_db=tmp_path / "unused.sqlite",
            upload_dir=tmp_path / "uploads",
        )
        output = tmp_path / "metadata.postgres.json"
        backup._backup_postgres(settings, output)
        payload = json.loads(output.read_text(encoding="utf-8"))

        tables = payload["tables"]
        assert set(backup.POSTGRES_TENANT_MAPPING_TABLES) <= set(tables)
        assert any(
            row["key_id"] == key.id and row["tenant_id"] == tenant_id
            for row in tables["service_key_tenants"]
        )
        assert any(
            row["job_id"] == job.id and row["tenant_id"] == tenant_id
            for row in tables["ingestion_job_tenants"]
        )
    finally:
        with pool.connection() as conn:
            if job is not None:
                conn.execute("DELETE FROM ingestion_job_tenants WHERE job_id=%s", (job.id,))
                conn.execute("DELETE FROM ingestion_jobs WHERE id=%s", (job.id,))
            if key is not None:
                conn.execute("DELETE FROM service_key_tenants WHERE key_id=%s", (key.id,))
                conn.execute("DELETE FROM service_keys WHERE id=%s", (key.id,))
        pool.close()


def test_postgres_restore_contract_accepts_legacy_archives_without_tenant_tables():
    assert backup.POSTGRES_REQUIRED_TABLES == (
        "documents",
        "service_keys",
        "security_audit",
        "ingestion_jobs",
    )
    assert backup.POSTGRES_TABLES == backup.POSTGRES_REQUIRED_TABLES + (
        "service_key_tenants",
        "ingestion_job_tenants",
    )
