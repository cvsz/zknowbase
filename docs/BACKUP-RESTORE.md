# zknowbase Local Backup & Restore Runbook

This runbook is for the self-hosted, zero-recurring-cost deployment. Backups stay on the local `backend_data` Docker volume unless you intentionally copy them to another machine/disk.

## What is backed up

A zknowbase archive contains:

- SQLite metadata database **or** the zknowbase-owned logical tables from local Postgres
- uploaded source files
- Qdrant collection snapshot when the collection exists
- `manifest.json` with SHA-256 + size for every component, metadata backend, collection name, and Qdrant version

The archive does **not** contain `.env`, model-provider credentials, Admin UI password hashes/session secret, TLS keys, or other deployment secrets. Back those up separately in an encrypted/offline secret store.

## Consistency model

The API and local ingestion worker hold a shared advisory `flock` on `/data/.mutation.lock` for data operations. Backup and restore take the exclusive form of the same lock.

Therefore:

1. an exclusive backup/restore waits for in-flight API/worker data operations;
2. new data operations wait until backup/restore releases the lock;
3. `/api/v1/health` remains available for orchestration;
4. restore does not expose a half-restored metadata/vector/file state through the normal API.

This coordination assumes the local containers share the same `backend_data` filesystem, as the supplied Compose deployment does. Do not use this file-lock design as a multi-host distributed lock.

## Create a backup

```bash
docker compose --profile ops run --rm backup backup
```

The command prints JSON containing the archive path and SHA-256. The default destination is:

```text
/data/backups/zknowbase-YYYYMMDDTHHMMSSZ.tar.gz
```

The archive is written with mode `0600`.

Choose an explicit local path inside the shared data volume:

```bash
docker compose --profile ops run --rm backup \
  backup --output /data/backups/before-upgrade.tar.gz
```

## Verify without restoring

```bash
docker compose --profile ops run --rm backup \
  verify /data/backups/before-upgrade.tar.gz
```

Verification rejects:

- missing/extra archive components;
- SHA-256 or size mismatch;
- traversal paths;
- symlinks/hard links/device entries;
- unsupported backup format.

Always verify a copied backup at its disaster-recovery destination, not only on the source host.

## Copy off the host

A local backup on the same disk is not disaster recovery. Copy the archive to another storage device/host using your existing local infrastructure. Example:

```bash
mkdir -p ./backups
CID=$(docker compose --profile ops create -q backup)
docker cp "$CID:/data/backups/before-upgrade.tar.gz" ./backups/
docker rm "$CID"
sha256sum ./backups/before-upgrade.tar.gz
```

Alternatively mount a dedicated local backup disk into the `backup` service and set `--output` there.

## Restore

Restore is destructive and requires `--yes`:

```bash
docker compose --profile ops run --rm backup \
  restore /data/backups/before-upgrade.tar.gz --yes
```

By default, the restore command first creates a **pre-restore safety backup** of the current state in `/data/backups` while it owns the exclusive data lock.

Only when storage space is critically constrained and you already have a verified rollback copy should you disable it:

```bash
docker compose --profile ops run --rm backup \
  restore /data/backups/before-upgrade.tar.gz --yes --no-safety-backup
```

## Restore prerequisites

The restore refuses to proceed when:

- backup metadata backend differs from the configured backend (`sqlite` vs `postgres`);
- Qdrant collection name differs;
- current Qdrant **major/minor** version differs from the backup;
- any manifest checksum/size verification fails.

Qdrant documents collection snapshots as compatible across patch releases of the same minor version; do not use this restore path to skip required Qdrant minor-version migrations.

## SQLite

SQLite backup uses Python's online `Connection.backup()` API, then runs `PRAGMA integrity_check` on the copied database. Restore also verifies integrity before copying the backup database into the configured SQLite database through SQLite's backup API.

Do not replace a live `.db` file with `cp`; use the provided command.

## Local Postgres

The Postgres path is self-hosted and does not require a managed database. zknowbase exports only its owned tables under a `REPEATABLE READ, READ ONLY` transaction:

- `documents`
- `service_keys`
- `security_audit`
- `ingestion_jobs`

Restore validates the expected table/column schema before its destructive transaction and uses quoted SQL identifiers. This logical format is deliberately application-scoped rather than a whole-cluster backup.

For a full local PostgreSQL cluster disaster-recovery policy (roles, unrelated databases, WAL/PITR), operate standard PostgreSQL backup tooling separately from zknowbase.

## Qdrant

The backup command asks local Qdrant to create a collection snapshot, streams that snapshot to disk (rather than buffering it in process memory), records SHA-256/size, then removes the temporary server-side snapshot.

Restore uploads the verified snapshot with:

- `priority=snapshot`
- SHA-256 checksum

If the backup was taken before the collection existed, restore removes the target collection so the restored vector state matches the backup's empty state.

## Recovery test cadence

A backup is not proven until restored. Recommended local procedure:

1. create backup;
2. copy it to a second disk/host;
3. verify the copied archive;
4. restore it into an isolated clone of the local stack running the same Qdrant minor version;
5. check `/api/v1/health`;
6. verify document count and a representative RAG query/citation;
7. record restore duration and archive SHA-256.

Repeat after storage/schema upgrades and periodically for production data.

## Important limitations

- The supplied `flock` coordination is for containers/processes sharing one local filesystem. It is not a distributed lock across independent hosts.
- The archive deliberately excludes deployment secrets; losing both `.env`/secret storage and all credentials will require credential reprovisioning.
- Qdrant snapshot recovery does not replace a documented staged Qdrant upgrade/migration procedure.
- Keeping archives only in the same Docker volume protects against logical mistakes but not disk/server loss; copy verified archives off-host/off-disk.
