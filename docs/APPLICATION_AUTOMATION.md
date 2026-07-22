# Application Automation

Graded automation. The hard invariant: **no formal submission without a per-job
human confirmation.**

## Level 1 — Auto prepare (no external page action)
Collect → parse → eligibility → resume select → build packet → draft answers →
select attachments.

## Level 2 — Browser-assisted fill (Chrome MV3 / optional local Playwright worker)
Identify the application page & fields; fill **confirmed deterministic** fields;
upload chosen files; save progress; flag uncertain questions; show answer source;
place open-ended drafts as **editable** text; check for missing fields and
job/material mismatch. Never submits.

## Level 3 — Final human confirmation (mandatory)
The confirmation page shows: company, role, official URL, resume used, cover
letter used, every answer, sensitive answers, work-authorization answer,
sponsorship answer, comp answer, terms agreement, possible risks, and everything
the system is unsure about. The user must actively click **Confirm and Submit**.
- No countdown auto-submit.
- Confirming one job never carries to another — **each job confirms separately**.
- On confirm, an immutable `application_confirmations` row is written binding the
  exact `packet_hash`; only then may the state machine advance to `submitted`.

## Level 4 — Not reliably automatable → manual mode with guidance
CAPTCHAs, complex Workday flows, unstable fields, video applications, online
assessments, legal attestations, voluntary demographics (disability/veteran/
diversity), signature-required statements. The system switches to manual and
gives clear instructions. **Never** bypass CAPTCHA or access controls.

## Submission state machine
See `app/applications/state_machine.py`. States and legal transitions are
enforced in code; `submitted` is unreachable without a valid confirmation. Full
state list is in DATA_MODEL.md / APPLICATION states.
