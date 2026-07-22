# Ranking Engine

Explainable **hybrid** scoring. The LLM never emits a single opaque total. The
score is a transparent weighted sum of per-dimension sub-scores, each with
evidence and confidence.

## Dimensions (built dynamically from the user's context/preferences)
hard-eligibility match · skill match · experience-evidence strength · role-direction
match · long-term career value · interview-likelihood · work-content quality ·
company quality · industry match · location/commute · compensation · work mode ·
job freshness · application cost · competition intensity · historical preference ·
**real historical outcomes**.

## Each dimension outputs
`score` (0..1), `weight` (from active `ranking_version`), `positive_evidence[]`,
`negative_evidence[]`, `uncertainty`, `confidence`.

## Total
```
total = Σ weight_i * score_i * confidence_i   (normalized by Σ weight_i)
```
Weights come from a **versioned** `ranking_version` (user-editable). Every score
is reproducible: same inputs + same version ⇒ same output (no nondeterministic LLM
in the numeric path; LLM, if used, only produces evidence text that is then
scored by rules).

## Outputs surfaced to the UI
total, per-dimension scores, positive/negative evidence, uncertainty, confidence,
why-recommended, why-maybe-not, suggested time investment, and a strategy label:
`Quick` / `Serious` / `Manual`.

## Outcome awareness
Ranking distinguishes: jobs the user *liked at the time* vs jobs that produced
*replies* vs *interviews* vs *final satisfaction*. The learning system feeds
calibrated adjustments (see LEARNING_SYSTEM.md). We optimize outcomes, not clicks
or raw application count.
