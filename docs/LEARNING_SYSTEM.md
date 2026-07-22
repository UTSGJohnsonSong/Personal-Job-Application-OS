# Learning System

A feedback loop that prioritizes **real outcomes** over clicks.

## Signals captured (`user_feedback`, `application_events`)
saves, skips (+reason), score edits, resume chosen, accepted/rejected wording
edits, packets actually submitted, replies, assessments, interviews, rejections,
offers, and post-interview satisfaction.

## Phase 1 (v1) — rules + stats, no black box
- Aggregate outcome rates by source / resume version / job type / company type.
- Detect common skill gaps among rejections.
- Produce **explainable weight-adjustment suggestions** for `ranking_versions`.
- Calibrate confidence via observed hit-rates (statistical calibration).

## Later phases (opt-in)
Learning-to-rank, bandits, Bayesian updating, outcome prediction, personalized
calibration.

## Guardrails
- Every automatic weight change is explainable, versioned, and **rollbackable**,
  shows its reason, can be turned off, and never silently alters *sensitive*
  preferences.
- Frequent clicks on a job type do **not** by themselves imply long-term fit;
  real outcomes (reply/interview/offer/satisfaction) dominate.
- Nothing here changes Personal Context facts — only ranking weights/calibration.
