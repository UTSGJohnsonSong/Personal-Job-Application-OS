# PRD — Personal Job Application OS

## 1. Vision
A single-user operating system for a job search. It continuously discovers jobs
(favoring first-party sources), understands the candidate from data they
explicitly provide, screens for eligibility, ranks openings with an explainable
score, prepares tailored application material, assists filling forms in the
browser, and tracks every application — while **learning from real outcomes**
(replies / interviews / offers), not just clicks.

## 2. Non-negotiable principles
1. First-party sources beat third-party reposts; store the canonical official URL.
2. Freshness first — a closed posting is never recommended as applyable.
3. Never presume the user's personal facts; everything comes from a Personal Context layer.
4. Never fabricate application facts (skills, experience, numbers, authorization, GPA).
5. Automate everything that is safe to automate.
6. Expose uncertainty; do not silently guess or silently skip.
7. **Every formal submission requires per-job human confirmation.** No auto-submit,
   no countdown auto-submit, no "you confirmed the last one" carry-over.
8. The user can always see, edit, export, and delete their data and see what data an
   application used.
9. Every automated decision is explainable.
10. Learning prioritizes real outcomes over click behavior.
11. Security and privacy outrank submission speed and volume.

## 3. Target user
The single owner/operator of the instance. There is exactly one human principal
per deployment. (Multi-tenant is explicitly out of scope for v1.)

## 4. Core jobs-to-be-done
- "Find me fresh, relevant, eligible jobs from real company sources."
- "Tell me *why* this job fits or doesn't, with evidence."
- "Prepare a tailored, truthful application packet I can review."
- "Fill the deterministic form fields for me, but stop before submit."
- "Track where every application stands and what I must do next."
- "Update statuses from recruiting emails without me copying anything."
- "Get better over time from what actually worked."

## 5. Scope (v1 / MVP)
See `MVP_ROADMAP.md`. In short: auth, Personal Context, resume import, source
management, Greenhouse/Lever/Ashby connectors + generic ATS interface, scheduled
sync, normalization, dedup, freshness verification, eligibility engine,
explainable ranking, Job Inbox, Job Detail, Dashboard, Resume Library,
Application Packet, Application Tracker, final-submit confirmation state machine,
Chrome extension basic assist, audit log, basic feedback loop, retryable sync,
tests/deploy/backup docs.

## 6. Explicitly out of scope (v1)
Unattended submission, CAPTCHA solving/bypass, LinkedIn/Indeed account automation,
auto-messaging recruiters, auto-accepting interviews, auto-answering
voluntary/legal/demographic disclosures, black-box scoring, and using unconfirmed
inferred personal context in a real application.

## 7. Success metrics
- Manual keystrokes per submitted application trend down over time.
- % of surfaced jobs that are eligible & fresh (precision of the inbox).
- Reply-rate, interview-rate, offer-rate tracked per source / resume version.
- Zero fabricated facts in submitted material (audited).
- Zero submissions without a recorded per-job confirmation (audited, hard invariant).

## 8. Key risks
- Source HTML/schema drift breaking connectors (mitigation: connector isolation,
  failure queue, contract tests).
- Ghost jobs / stale reposts (mitigation: freshness re-verification, canonicalization).
- Over-eager LLM inference introducing false facts (mitigation: provenance +
  confirmation gates + schema validation + evidence requirement).
- PII leakage into logs / LLM payloads (mitigation: redaction + PII minimization).
