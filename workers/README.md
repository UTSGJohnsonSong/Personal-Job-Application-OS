# Workers

Background jobs for Personal Job Application OS. The task-queue backend is
pluggable (Dramatiq/Celery/RQ — see docs/DECISIONS.md D6); this directory holds
the entrypoints and schedules.

## Jobs
- `sync_sources` — incremental connector sync (ETag/Last-Modified aware).
- `reverify_freshness` — deadline-/target-aware re-verification.
- `email_sync` — recruiting-email status updates (requires user OAuth; deferred).
- `generate_documents` — packet material generation.
- `evaluate_learning` — outcome aggregation + calibration suggestions.
- `reminders` — deadlines, assessments, stale applications.

## Invariants
Every job is idempotent, resumable, observable, retried with backoff, and
failure-isolated (one source failing never blocks others). See
`apps/api/app/ingestion/sync.py` for the idempotent ingestion core.

## Local run (no broker required)
```bash
cd apps/api
./.venv/Scripts/python -m app.workers.tasks sync --connector greenhouse --board exampleco
```
