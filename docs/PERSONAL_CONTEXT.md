# Personal Context

The Personal Context Layer is the **single source of truth** about the user. No
personal fact used in judgement or application may originate anywhere else. The
system ships with **zero** presumed facts.

## Item protocol
Every fact (whether a generic `personal_context_items` row or a typed field on a
structured entity) records:

| field | meaning |
|---|---|
| `value` | the fact |
| `source` | `ProvenanceSource` (see DATA_MODEL.md) |
| `confidence` | 0..1 model/heuristic confidence when inferred; 1.0 for user-confirmed |
| `user_confirmed` | boolean; user has explicitly affirmed this value |
| `last_confirmed_at` | timestamp of last affirmation |
| `can_use_for_application` | may this feed a real application? (requires confirmation) |
| `sensitivity_level` | `low` / `pii` / `sensitive_legal` (auth, demographics, GPA…) |
| `notes` | free text |

## Rules
- Inferred-but-unconfirmed items **may inform ranking/eligibility as signals** but
  are **never** written into application material or answers.
- Resume-extracted items start `user_confirmed = false`; the user confirms in a
  review flow before they become application-usable.
- The user can: view everything the system knows, edit, delete, mark
  "do-not-use-for-application", export (JSON), revoke authorization, and see
  exactly which items a given application used (via audit log).

## No inference of these from thin signals
Never infer identity/authorization/skills from a name, a location, or a school.
Never upgrade "familiar with" → "expert", "participated" → "led", or a guess → a
fact. These are hard rules in the parsing and generation layers.

## Structured entities
`candidate_profiles / experiences / projects / education / skills /
work_authorizations / application_preferences / standard_answers` all extend the
item protocol so provenance travels with structured data too.

## Sensitivity handling
`sensitive_legal` items (work authorization details, GPA, demographics) are:
- never sent to a cloud LLM when `LLM_STRICT_PII_MINIMIZATION=true`,
- redacted in logs,
- require an extra explicit confirmation before use in any answer,
- for voluntary demographic/disability/veteran questions: **never auto-answered**
  (v1 forces manual mode).
