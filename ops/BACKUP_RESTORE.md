# Backup and Restore Playbook

This playbook covers backup and restore operations for Brainstem storage.

## Scope

- Memory store (SQLite or Postgres)
- Model registry store (SQLite or Postgres)

## SQLite backup

Run:

```bash
bash scripts/backup_sqlite.sh \
  --memory-db .data/brainstem.db \
  --registry-db .data/model_registry.db \
  --out-dir backups/sqlite/latest
```

Artifacts:

- `memory.db`
- `model_registry.db`
- `checksums.txt`
- `manifest.json`

## SQLite restore

Run:

```bash
bash scripts/restore_sqlite.sh \
  --backup-dir backups/sqlite/latest \
  --memory-db .data/brainstem.db \
  --registry-db .data/model_registry.db
```

Notes:

- Existing destination files are snapshot-copied to
  `*.pre_restore.<timestamp>`.
- If checksums are present, integrity is verified before restore.

## PostgreSQL backup

Run:

```bash
bash scripts/backup_postgres.sh \
  --dsn "postgresql://postgres:postgres@localhost:5432/brainstem" \
  --out-dir backups/postgres/latest
```

Artifacts:

- `brainstem.pgdump`
- `schema.sql`
- `checksums.txt`
- `manifest.json`

## PostgreSQL restore

Run:

```bash
bash scripts/restore_postgres.sh \
  --dsn "postgresql://postgres:postgres@localhost:5432/brainstem" \
  --backup-file backups/postgres/latest/brainstem.pgdump
```

## Recovery smoke test (SQLite)

Run:

```bash
python scripts/verify_sqlite_restore.py
```

This command:

1. seeds memory + model registry data into source SQLite files,
2. runs backup and restore scripts,
3. verifies restored recall + registry history,
4. writes report JSON to `.data/restore-verify/verification.json`.

## Operational checklist

1. Confirm latest successful backup timestamp from `manifest.json`.
2. Verify checksum integrity before restore.
3. Restore to staging first and run smoke verification.
4. Run API health and recall smoke checks after production restore.
5. Record incident timeline and restored snapshot id.

## Recovery time target

With local SSD and typical v0 dataset sizes, SQLite restore + verification is
expected to complete in under 30 minutes.

