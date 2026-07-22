# Audit

## Goals
Every consequential action is reconstructable: who/what changed personal data,
who generated answers, which model produced them, which sources were used, what
was auto-filled, what the user confirmed, when a submission happened, and what
external systems returned.

## `audit_logs` schema (append-only)
`id, occurred_at, actor (user|system|connector|extension|worker), action,
entity_type, entity_id, summary, metadata(jsonb, PII-redacted), model_run_id?,
request_id`. No UPDATE/DELETE granted to the application DB role.

## Events that MUST be audited
- Personal Context create/edit/delete/confirm/revoke.
- Resume/document upload & generation.
- LLM calls (purpose, model, data scope — never raw sensitive payload).
- Eligibility & ranking computation (version + inputs hash).
- Packet build & each answer's provenance.
- **Pre-submit confirmation** (immutable, links packet_hash).
- Submission and external responses.
- Email-driven status changes (source + confidence).
- Connector failures and quarantine actions.

## Integrity
Optional hash-chaining (`prev_hash`) so tampering is detectable. Audit records
carry no full PII — only references and redacted metadata.
