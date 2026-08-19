# Tenant-aware backup/restore

Postgres backups include the durable tenant ownership tables `service_key_tenants`, `ingestion_job_tenants`, and `security_audit_tenants` in addition to the core metadata tables. Restoring a current backup therefore preserves service-key, async-ingestion, and immutable security-audit tenant ownership exactly, including bootstrap operations explicitly attributed to a target tenant.

Format-version 1 archives created before tenant isolation remain supported. If any tenant mapping table is absent during restore, the restore leaves that mapping table empty. Service keys and ingestion jobs are deterministically assigned to `ZKB_DEFAULT_TENANT_ID` when first observed. Legacy audit records fall back to the restored service-key tenant mapping; anonymous records remain unscoped. This preserves backward compatibility without guessing a tenant from client input.

SQLite backups already copy the entire database file, so all tenant mapping tables are included automatically.
