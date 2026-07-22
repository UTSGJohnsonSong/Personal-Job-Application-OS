# Backup & Restore

## What to back up
1. Database (Postgres in prod / SQLite file in dev).
2. Private object storage bucket (resumes, transcripts, offer docs).
3. Secrets are NOT backed up here — they live in a secret manager.

## Postgres backup
```bash
pg_dump "$DATABASE_URL" --format=custom --file=backup_$(date +%F).dump
```

## Postgres restore (into a fresh DB)
```bash
createdb job_os_restore
pg_restore --dbname=job_os_restore --clean --if-exists backup_YYYY-MM-DD.dump
```

## Object storage (MinIO/S3)
```bash
mc mirror local/job-os-private ./backups/objstore/$(date +%F)
```

## SQLite (dev)
```bash
cp apps/api/data/job_os.db backups/job_os_$(date +%F).db
```

## Restore test (run regularly — a backup you haven't restored is a guess)
1. Restore the dump into a scratch DB.
2. Run `alembic current` to confirm the schema head matches.
3. Run the API smoke test against the restored DB:
   `pytest apps/api/tests/test_api.py -q`.
4. Verify row counts for `jobs`, `applications`, `audit_logs` are non-decreasing
   vs the prior known-good snapshot.

## Deletion propagation
User hard-delete requests must be applied to the primary store AND purged from
backups within one backup rotation cycle (see docs/PRIVACY.md).
