# Tenant-aware backup/restore

Postgres backups include the durable tenant ownership tables `service_key_tenants` and `ingestion_job_tenants` in addition to the core metadata tables. Restoring a current backup therefore preserves service-key and async-ingestion tenant ownership exactly.

Format-version 1 archives created before tenant isolation remain supported. If either tenant mapping table is absent during restore, the restore leaves that mapping table empty and the tenant wrappers deterministically assign restored legacy service keys and ingestion jobs to `ZKB_DEFAULT_TENANT_ID` when first observed. This preserves backward compatibility without guessing a tenant from client input.

SQLite backups already copy the entire database file, so tenant mapping tables are included automatically.
