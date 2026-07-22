# Data Model

Every meaningful record carries: `created_at`, `updated_at`, `version`, and where
it represents a claim about the user or the world: `source`, `provenance`,
`confidence`, `user_confirmed`. Soft-delete (`deleted_at`) is used for
user-facing content; audit logs are append-only.

## Provenance vocabulary (enum `ProvenanceSource`)
`user_confirmed` · `resume_extracted` · `imported_document` ·
`inferred_but_unconfirmed` · `generated_draft` · `connector` · `email_ingest` ·
`system`.

Only `user_confirmed` (and, per-field, explicitly whitelisted `resume_extracted`
that the user has confirmed) may set `can_use_for_application = true`.

## Entity groups

### Identity & settings
- **users** — the single principal (email, hashed password, mfa_secret?, status).
- **user_settings** — timezone, locale, notification prefs, LLM opt-in flags.

### Personal Context (see PERSONAL_CONTEXT.md)
- **personal_context_items** — generic key/value facts with full provenance.
- **candidate_profiles**, **candidate_experiences**, **candidate_projects**,
  **candidate_education**, **candidate_skills** — structured resume data.
- **work_authorizations** — status per country, needs_sponsorship, evidence.
- **application_preferences** — locations, remote pref, comp, company size,
  industries, dealbreakers, weight overrides.
- **standard_answers** — reusable answers to common application questions.

### Documents & resumes
- **resume_versions**, **resume_sections**, **resume_bullets** — library with
  base + direction variants; bullets keep original + tailored + rationale.
- **documents** — uploaded/generated files (private object storage keys, hashes).

### Companies & sources
- **companies**, **company_domains**, **company_aliases**, **company_career_pages**.
- **job_sources** — a configured source (e.g., "Greenhouse:acme").
- **source_connectors** — connector type + config + health.
- **source_sync_runs** — every sync attempt (idempotency key, stats, status, error).

### Jobs
- **jobs** — canonical job with freshness/status fields (see FRESHNESS_STRATEGY.md).
- **job_snapshots** — content hash history per fetch (drift + repost detection).
- **job_requirements** — structured, evidence-bearing extracted requirements.
- **job_locations**, **job_embeddings** (pgvector), **duplicate_groups**.

### Matching
- **eligibility_results** — verdict + reasons + evidence + needs_user_confirmation.
- **ranking_profiles**, **ranking_versions** — weight sets, versioned.
- **job_matches**, **match_dimensions**, **match_evidence** — explainable score.

### Applications
- **application_packets**, **generated_documents**, **application_answers**.
- **applications** — one per (user, job); status = submission state machine.
- **application_events** — full timeline.
- **application_confirmations** — the immutable per-job pre-submit confirmation record.

### Email & learning & ops
- **email_connections**, **email_events**.
- **user_feedback**, **learning_updates**, **model_runs**.
- **connector_failures**, **notifications**, **audit_logs**.

## Key invariants (enforced in code + constraints)
- Unique `(source_id, source_job_id)` on jobs; unique canonical URL where present.
- A job cannot be `submitted` unless a matching `application_confirmations` row
  exists whose `confirmed_at` is set and `packet_hash` matches the submitted packet.
- `personal_context_items.can_use_for_application` implies `user_confirmed = true`.
- `audit_logs` are append-only (no UPDATE/DELETE via the app role).

See `apps/api/app/models/` for the authoritative schema and
`alembic` migrations for the concrete DDL.
