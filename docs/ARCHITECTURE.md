# Architecture

## Monorepo layout
```
apps/
  web/            Next.js + TS + Tailwind + shadcn/ui + React Query (control center UI)
  api/            FastAPI + Pydantic + SQLAlchemy + Alembic (core domain + engines)
  extension/      Chrome MV3 extension (deterministic form assist, submit intercept)
workers/          Background jobs entrypoints (sync, freshness, email, learning)
packages/
  schemas/        Shared JSON Schemas / TS types generated from Pydantic (contract)
infrastructure/   docker-compose, deploy notes, backup/restore scripts
docs/             Design docs (source of truth for intent)
```

The backend is deliberately layered so business logic never lives in route
handlers. The Python package is `app` (under `apps/api`):

```
app/
  core/          config, logging, security primitives, provenance enums
  db/            engine/session, base model mixins
  models/        SQLAlchemy ORM (see DATA_MODEL.md)
  schemas/       Pydantic I/O + LLM structured-output schemas
  connectors/    source plugins (base + greenhouse/lever/ashby/generic)
  ingestion/     normalization, dedup, freshness verification, sync orchestration
  parsing/       JD structured extraction (rule-based + optional LLM), resume parsing
  eligibility/   eligibility engine (explainable, evidence-bearing)
  ranking/       explainable hybrid scoring (dimensions, weights, versions)
  personal/      Personal Context service (provenance, confirmation, permissions)
  applications/  packet building, submission state machine, tracker
  learning/      feedback capture + calibration (rules/stats first)
  api/           FastAPI routers (thin; call services)
  services/      orchestration services tying the layers together
  seed/          fully fictional seed data
```

## Data plane
- **PostgreSQL + pgvector** in production (embeddings for dedup/semantic match).
  SQLite is supported for zero-infra local dev/tests (see DECISIONS.md).
- **Redis** for queues, rate-limit tokens, caches.
- **S3-compatible private object storage** for resumes, transcripts, offer docs
  (signed URLs, never public).

## Background jobs
A reliable task system (Dramatiq/Celery/RQ — pluggable; interface in `workers/`).
Jobs: incremental source sync, targeted-company high-frequency checks,
deadline-driven re-verification, email sync, document generation, model/rule
evaluation, reminders. All jobs are **idempotent, resumable, observable, retried
with backoff, failure-isolated** (one source failing never blocks others).

## Request/trust boundaries
- JD text and any scraped web content are **untrusted input**. They can never
  override system rules, exfiltrate PII, or trigger tools. See THREAT_MODEL.md.
- The extension holds least privilege and cannot submit without the confirmation
  gate. See APPLICATION_AUTOMATION.md.

## Diagram (logical)
```
[Sources: Greenhouse/Lever/Ashby/Official ATS/Gov/Univ/Aggregators]
        | connectors (rate-limited, retried, ETag/Last-Modified)
        v
   [Ingestion] normalize -> dedup -> freshness-verify
        v
   [Parsing] JD -> structured requirements (schema-validated, evidence kept)
        v
   [Eligibility] evidence-bearing verdicts  <----+
        v                                        |
   [Ranking] explainable dimensions/weights      | Personal Context (single
        v                                        | source of truth for the user)
   [Job Inbox / Detail / Dashboard] <------------+
        v
   [Application Packet] resume select + tailoring + answers (provenance)
        v
   [Submission State Machine] -> HUMAN CONFIRM (per job) -> Submitted
        v
   [Tracker] timeline + email-driven status updates
        v
   [Learning] outcomes -> calibration -> weight suggestions (explainable, versioned)
```
