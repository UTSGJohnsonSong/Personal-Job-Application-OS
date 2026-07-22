# Ranking Migration — v1 → v2

## What was wrong in v1

| # | Defect | Location | Consequence |
|---|---|---|---|
| 1 | `hard_eligibility` counted **twice** — weighted dimension (3.0) *and* `min(total, 0.15)` cap | `ranking/engine.py` | eligibility both added score and vetoed it |
| 2 | One opaque `total_score` (`0.931`) | `ranking/engine.py` | read as "93% match / 93% interview odds / 93% career value" |
| 3 | Skill match by **substring** — `"sql" in "postgresql"` | `seed/seed_data.py` | false SQL match |
| 4 | Role direction by **title substring** — `role in title` | `_score_role` | `Sales Engineer` → software engineering |
| 5 | Fake prior: `historical_outcome = 0.5, confidence 0.3` | `_simple(...)` | invented a data point |
| 6 | `company_quality` hand-fed (`0.7`) | `seed_data.py` | unsourced |
| 7 | Arbitrary thresholds `0.6 / 0.72 / 0.5` | seed + engine | uncalibrated |
| 8 | Freshness (1.0) and application cost (0.7) inside the value sum | `DEFAULT_WEIGHTS` | new/easy jobs looked *better*, not just *sooner* |

## v2 structure

```
Eligibility Gate (PASS/REVIEW/FAIL)   ← no longer a score at all
        ↓ PASS only
six independent scores + Evidence Coverage
        ↓
Tier × Role rules + platform multiplier × transferability
        ↓
Application Priority 0–100   (NEVER rendered as "% match")
```

## New formulas

```
Known-Evidence = Σ(w·s·c) / Σ(w·c)
Coverage       = Σ(w·c)   / Σ(w)
Conservative   = Known·Coverage + 0.5·(1 − Coverage)     # 0.5 is a labelled prior

Priority_base  = Σ(mode_weight_i · conservative_i) / Σ(mode_weight_i)
effective_bonus= (platform_multiplier[tier] − 1) × role_transferability
Priority       = Priority_base × (1 + effective_bonus)  [+3 if deadline <72h]
Gate FAIL      → Priority = min(Priority, 5)
```

## Internship Mode weights

`company 50% · role_strategic 20% · team 12% · fit 10% · opportunity 5% · freshness+effort 3%`

## Migration rules

1. **Old results are not deleted.** Existing `job_matches` rows keep their data.
2. Legacy rows are stamped `formula_version = "legacy-v1"`; v2 rows use `"v2"`.
3. v2 writes to new tables so both orderings coexist and can be diffed.
4. Seed jobs are recomputed under v2 on migration.
5. The UI can show *why the order changed* by comparing versions.
6. Regression tests pin the v2 ordering guarantees (`tests/test_ranking_v2.py`).
7. DB migration is additive — no destructive column drops.
8. API returns the six scores plus coverage; the single `total_score` field is
   retained on legacy rows only.

## Expected ordering changes on the existing seed data

| Job | v1 | v2 | Why |
|---|---|---|---|
| Software Engineer, Backend | `0.931` "strong match" | Priority driven by company tier + R1 transferability | fit no longer dominates; platform does |
| Machine Learning Engineer (PhD required) | `0.15` capped | Gate **FAIL** → Priority ≤ 5, `Skip (ineligible)` | eligibility is a gate, not a −score |

Note both seed companies currently have **no evidence rows**, so their platform
value is `Unrated / needs research` — v2 refuses to invent a company tier. This
is the intended behaviour, and is why real company evidence is the next task.

## Still required before v2 is fully trustworthy

- Real company evidence collection (the research pipeline) — until then most
  companies sit at low coverage and get conservative, deliberately unconfident
  scores.
- Real personal outcome data — Opportunity Estimate stays "Insufficient
  Personal Outcome Data" and contributes a neutral, labelled component.
- Pairwise preference capture to calibrate the platform-vs-fit trade-off.
