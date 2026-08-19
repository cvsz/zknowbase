# zknowbase Backup and Restore Runbook

## Scope

This runbook covers the self-hosted zknowbase data plane: SQLite or local Postgres metadata, uploaded source files, and Qdrant collection snapshots. The implementation is local-first and does not require managed backup services.

## Data covered by a backup

A zknowbase backup archive contains:

- `manifest.json` with format version, component sizes, SHA-256 checksums, metadata backend, Qdrant collection name, and Qdrant version.
- `metadata.sqlite` when `ZKB_METADATA_BACKEND=sqlite`, or `metadata.postgres.json` when `ZKB_METADATA_BACKEND=postgres`.
- `uploads.tar.gz` containing uploaded source files.
- `qdrant.snapshot` when the configured Qdrant collection exists.

Archives are created with owner-only filesystem permissions (`0600`).

## Preconditions

1. Backend dependencies are installed and the same configuration used by the running deployment is available to the CLI.
2. Qdrant is reachable from the backend runtime.
3. For Postgres mode, `ZKB_POSTGRES_URL` points to the target local/self-hosted Postgres instance.
4. The process has write access to `ZKB_BACKUP_DIR` and `ZKB_UPLOAD_DIR`.
5. For restore, the configured metadata backend and Qdrant collection must match the backup manifest.

## Create a backup

From the backend directory:

```bash
python -m app.backup backup
```

To choose an explicit path:

```bash
python -m app.backup backup --output /data/backups/zknowbase-manual.tar.gz
```

Expected output is JSON containing the archive path and SHA-256 digest.

## Verify a backup without restoring

```bash
python -m app.backup verify /data/backups/zknowbase-manual.tar.gz
```

Verification fails closed when:

- the archive format version is unsupported;
- required components are missing;
- unexpected files exist in the archive;
- component size or SHA-256 checksum does not match the manifest;
- an archive member attempts path traversal or contains unsafe links/devices.

## Restore procedure

Restore is destructive and requires explicit confirmation:

```bash
python -m app.backup restore /data/backups/zknowbase-manual.tar.gz --yes
```

By default the restore path creates a pre-restore safety backup before mutation. Disable that only when recovery storage is unavailable and the operator has another verified recovery point:

```bash
python -m app.backup restore /data/backups/zknowbase-manual.tar.gz --yes --no-safety-backup
```

The restore implementation acquires the exclusive mutation lock, validates the archive before mutation, validates Qdrant major/minor compatibility, restores the Qdrant snapshot or deletes the collection when the backup had no snapshot, replaces uploaded files through a staging directory, and restores the configured metadata backend.

## SQLite recovery notes

SQLite backup and restore use the SQLite backup API and run `PRAGMA integrity_check` on the backup source before applying it. The default single-node deployment should stop application traffic before a disaster-recovery restore even though the mutation lock prevents zknowbase-managed mutations.

## Postgres recovery notes

Postgres backup is captured under a repeatable-read read-only transaction. Restore ensures the current schemas exist, then restores zknowbase-owned tables in a destructive transaction. Use a dedicated zknowbase database or schema boundary; do not point the restore command at a shared database where truncating zknowbase tables would violate another application's ownership assumptions.

## Qdrant compatibility

The backup records the Qdrant server version. Restore requires the current server to match the backup's major and minor Qdrant version. Patch-level differences are accepted. If the versions are incompatible, upgrade or downgrade the target Qdrant service first and retry verification/restore.

## Disaster-recovery drill

Run this drill before production release and after material storage changes:

1. Create a backup from a seeded environment containing at least one document and vectors.
2. Copy the archive to a separate filesystem or host.
3. Run `python -m app.backup verify <archive>` on the copied artifact.
4. Record archive SHA-256, size, creation time, metadata backend, and Qdrant version.
5. Restore into an isolated environment configured with the same metadata backend and Qdrant collection.
6. Confirm documents are listed, uploaded files match expected SHA-256 hashes, vector search returns the seeded source, and API-key authorization still behaves correctly.
7. Delete or mutate the seeded data, restore again from the same archive, and confirm repeatability.
8. Record measured RPO and RTO for the drill.

## Recommended policy

- Development: manual backup before destructive migrations.
- Single-node production: scheduled daily backup plus an additional backup before upgrades.
- HA/local Postgres production: daily application-level backup plus independent infrastructure-level Postgres backup if available.
- Retain at least three known-good recovery points and store at least one copy outside the host running zknowbase.
- Periodically restore a retained archive into an isolated environment; backup creation alone is not recovery evidence.

## Failure handling

Do not retry a failed restore blindly after partial external-system failure. Preserve the error output, verify whether Qdrant, uploads, or metadata was already changed, and use the automatically created pre-restore safety backup when available. If the safety backup failed to complete, stop mutation traffic and recover from the most recent separately verified archive.

## Release evidence

A production release should retain evidence for:

- successful `backup` command;
- successful `verify` command;
- successful isolated restore drill;
- backend test coverage for SQLite/Postgres/Qdrant backup paths;
- archive permission check (`0600`);
- measured RPO/RTO and operator sign-off.
