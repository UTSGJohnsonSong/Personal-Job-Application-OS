# Personal Job Application OS

## ▶ Live

| | |
|---|---|
| **Web — start here** | **https://personal-job-application-os-web-lemon.vercel.app** |
| **Board (the working screen)** | **https://personal-job-application-os-web-lemon.vercel.app/board** |
| API | https://job-os-api-jstp.onrender.com · docs at `/docs` |

> The API is on a free plan and sleeps after ~15 minutes idle. The first request
> of the day takes roughly 50 seconds to wake it — the web app will look stuck
> until it answers. Both sides are protected by the same `API_TOKEN`.

---

A single-user operating system for a job search. It continuously discovers jobs
(favoring **first-party** sources), understands the candidate from data they
explicitly provide, screens **eligibility**, ranks with an **explainable** score,
prepares tailored application material, assists filling forms in the browser, and
tracks every application — while **learning from real outcomes** (replies /
interviews / offers), not clicks.

> **The hard invariant:** every formal submission requires a **per-job human
> confirmation**. No auto-submit, no countdown, no carry-over. Enforced in code
> (`app/applications/state_machine.py`) and in the browser extension.

See [`docs/`](docs/) for the full design (PRD, architecture, data model,
personal-context protocol, freshness strategy, connector interface, eligibility
& ranking engines, application automation, learning, security, threat model,
privacy, audit, roadmap, decisions).

## Status (this build)
| Area | State |
|---|---|
| Design docs (18) | ✅ complete |
| Monorepo + infra (docker-compose, .env.example, SQLite fallback) | ✅ |
| Data model (47 tables) + Alembic migration | ✅ runs |
| Connectors: Greenhouse, Lever, Ashby, generic ATS | ✅ + contract tests |
| Ingestion: normalize, dedup ladder, freshness, idempotent sync | ✅ |
| JD parsing (rule-based) + resume parsing | ✅ |
| Eligibility engine (explainable, evidence-bearing) | ✅ |
| Ranking engine (explainable hybrid, reproducible) | ✅ |
| Submission state machine + per-job confirmation | ✅ + tests |
| Dashboard / Jobs / Applications API | ✅ |
| Fictional seed data | ✅ |
| Backend tests / lint / type-check | ✅ 24 tests, ruff, mypy clean |
| Web (Next.js) Dashboard + Inbox | 🟡 skeleton, wired to API |
| Chrome extension (MV3) submit-intercept | 🟡 skeleton |
| Email/status sync, full learning loop, auth UI | ⛔ interfaces only (deferred) |

## Repo layout
```
apps/api/         FastAPI backend + engines (the core)
apps/web/         Next.js control center (dashboard, inbox)
apps/extension/   Chrome MV3 form-assist + submit intercept
workers/          Background job entrypoints
packages/schemas/ API contract (OpenAPI -> TS types)
infrastructure/   backup/restore, deploy notes
docs/             design docs (source of truth)
```

## Quick start (backend — zero infrastructure, SQLite)
```bash
cd apps/api
python -m venv .venv
./.venv/Scripts/python -m pip install -e ".[dev]"     # Windows
# source .venv/bin/activate && pip install -e ".[dev]" # macOS/Linux

alembic upgrade head                 # create schema
python -m app.seed.seed_data         # fictional demo data (no real PII)
uvicorn app.main:app --reload        # http://localhost:8000/docs
```

Run the checks:
```bash
ruff check app tests    # lint
mypy app                # type check
pytest -q               # 24 tests
```

## Quick start (web)
```bash
cd apps/web
npm install
npm run dev              # http://localhost:3000  (expects API on :8000)
```

## Quick start (extension)
Load `apps/extension/` as an unpacked extension in Chrome (Developer Mode).
It fills only confirmed deterministic fields and **blocks** any final submit.

## Full infrastructure (optional)
```bash
docker compose up -d     # Postgres+pgvector, Redis, MinIO
# set DATABASE_URL=postgresql+asyncpg://job_os:job_os@localhost:5432/job_os in .env
cd apps/api && alembic upgrade head
```

## Deploy notes
- **API**: containerize `apps/api` (uvicorn/gunicorn workers), point
  `DATABASE_URL` at managed Postgres+pgvector, `REDIS_URL` at managed Redis,
  S3-compatible private bucket for documents. Run `alembic upgrade head` on
  release. Health: `/health`, `/health/db`.
- **Web**: `apps/web` deploys to any Next.js host (e.g. Vercel); set
  `NEXT_PUBLIC_API_BASE`.
- **Workers**: run `app.workers.tasks` under a scheduler / task queue.
- **Backups**: see `infrastructure/BACKUP_RESTORE.md` (with a restore test).
- Production deploy to a public environment is intentionally left to the user
  (requires real secrets / infra decisions).

## Safety & privacy posture
- No presumed personal facts; everything flows through the Personal Context layer
  with provenance + confirmation gates.
- No fabricated application facts (skills/experience/numbers/authorization/GPA).
- JD/web text is untrusted input (prompt-injection resistant design).
- PII minimization for any LLM use; the system runs fully offline (rule-based)
  with no LLM configured.
- Append-only audit log; per-application data-use trace.

See `docs/SECURITY.md`, `docs/THREAT_MODEL.md`, `docs/PRIVACY.md`.
