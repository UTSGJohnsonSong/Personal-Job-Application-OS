# Privacy

## Principles
- The system stores **only** what the user provides or the system produces from
  it. No presumed personal facts. No third-party data brokering.
- The user owns the data and controls its use per item
  (`can_use_for_application`, `sensitivity_level`).

## User rights (implemented as first-class features)
- **See**: view every stored item and its provenance/confidence/confirmation.
- **Edit / delete**: any item; soft-delete then purge.
- **Restrict**: mark items not-for-application.
- **Export**: full JSON export of Personal Context + applications.
- **Revoke**: disconnect email/OAuth and third-party connectors; keys destroyed.
- **Trace**: for any application, see exactly which items were used (audit log).

## Data minimization
- Sensitive-legal data never leaves the instance to a cloud LLM under strict mode.
- Only the fields required for a given operation are loaded/sent.
- Logs are redacted; object storage is private with signed URLs.

## Retention
Closed/expired jobs are archived (kept for learning, out of the applyable inbox).
User content honors soft-delete then hard-delete on request. Backups follow the
same deletion within one backup cycle (documented in infrastructure/).
