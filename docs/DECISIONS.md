# Decisions (ADR log)

Format: Decision — Context — Choice — Tradeoff — Revisit.

## D1 — DB engine for dev/tests: SQLite; prod: Postgres+pgvector
- Context: The session must actually run migrations + tests without guaranteeing a
  running Postgres. Spec mandates Postgres+pgvector for production.
- Choice: SQLAlchemy models portable across both. `DATABASE_URL` selects engine.
  pgvector-specific columns degrade to JSON/text on SQLite (embeddings stored but
  ANN search only on Postgres). Alembic migration is written portably.
- Tradeoff: Vector similarity dedup is exact/brute-force on SQLite. Fine for dev.
- Revisit: When deploying, run on Postgres and enable the pgvector index migration.

## D2 — Async stack
- FastAPI + async SQLAlchemy (`sqlite+aiosqlite` / `postgresql+asyncpg`). Uniform
  async across API and workers.

## D3 — Connectors: use official public JSON board APIs
- Greenhouse/Lever/Ashby expose the *company's own* board JSON. First-party,
  canonical URLs, no auth, polite. Contract-tested against recorded fixtures; no
  live network in CI.

## D4 — No LLM required to run
- All numeric paths (eligibility, ranking, freshness, dedup) are deterministic
  rule/stat code. LLM is an optional enricher for JD parsing text and wording,
  behind a provider flag, with schema validation + PII minimization. This keeps
  scores reproducible and the system runnable offline.

## D5 — Submission safety as a code invariant, not a convention
- `submitted` state is unreachable unless an immutable `application_confirmations`
  row exists whose `packet_hash` matches. Enforced in the state machine + a DB
  check. Chrome extension physically cannot submit.

## D6 — Task queue abstracted
- Interface in `workers/`; default runnable in-process/CLI. Dramatiq/Celery/RQ
  pluggable later. Avoids forcing a broker for local runs.

## D7 — Single-principal
- Exactly one user per deployment; no multi-tenant. Simplifies authz to
  owner-only. Revisit only if sharing is ever needed.

## Open questions
- Which task queue to standardize on for prod (leaning Dramatiq for simplicity).
- Workday/iCIMS connectors need per-tenant handling; deferred past MVP.
- Local LLM runtime choice (Ollama vs llama.cpp) for the privacy mode.
