# MVP Roadmap

## Phase 0 — Repo check ✅
Greenfield; monorepo initialized.

## Phase 1 — Design docs ✅
All docs in `docs/`.

## Phase 2 — Infrastructure ✅ (this session)
Monorepo, docker-compose (Postgres+pgvector/Redis/MinIO), .env.example,
SQLite fallback for dev/tests, structured logging, health checks, error handling,
test fixtures.

## Phase 3 — Personal Context ✅ (core)
Provenance-bearing items, confirmation gate, permission flags. Import/parse is
stubbed with a rule-based resume parser; LLM optional.

## Phase 4 — Job sources ✅ (Greenhouse/Lever/Ashby + generic interface)
Contract tests via fixtures. Rate limit, retry, freshness, source metadata,
failure isolation.

## Phase 5 — Job processing ✅
Normalization, dedup (ladder), rule-based JD parsing, freshness verification,
eligibility, explainable ranking.

## Phase 6 — Web application 🟡 (this session: Dashboard + Inbox skeleton)
Remaining pages scaffolded; wired to API contract.

## Phase 7 — Browser assist 🟡 (MV3 skeleton with submit-intercept)

## Phase 8 — Email/status sync ⛔ (interfaces + models present; OAuth requires user)

## Phase 9 — Learning 🟡 (feedback capture + calibration scaffold)

## Delivered this session (MVP slice)
Items 1–17, 19, 20–23, 25–28 of the spec's Phase-1 list are implemented as a
runnable, tested backend core + UI/extension skeletons. See README "Status".

## Deferred (require the user / explicit go)
Real personal data, email OAuth connect, live network sync in CI, production
deploy, paid LLM usage.
