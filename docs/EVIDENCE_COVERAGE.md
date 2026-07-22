# Evidence Coverage

The system must never present a precise-looking score built on thin evidence.
Every composite score is reported as a triple.

## The three numbers

```
Known-Evidence Score = Σ(w · score · confidence) / Σ(w · confidence)
Evidence Coverage    = Σ(w · confidence) / Σ(w)
Conservative Score   = Known-Evidence · Coverage + NeutralPrior · (1 − Coverage)
```

`NeutralPrior` defaults to 0.5 in v1 and is **explicitly labelled a prior**, not
an observation.

Display all three:

```
Known-Evidence Fit: 93%
Evidence Coverage:  66%
Conservative Fit:   78%
```

Never display `Match: 93%` alone.

## Unknown dimensions

A genuinely unknown dimension is recorded as:

```
score = null
confidence = 0
```

It contributes nothing to the numerator and nothing to coverage. If a prior is
used instead, it MUST be flagged `is_prior = true` and must not be rendered in
the UI as an observed dimension score.

This replaces the old behaviour of silently substituting `0.5 / confidence 0.3`,
which faked precision.

## Coverage bands

```
< 40%      Unrated / Needs Research
40–64%     Provisional Tier          (render as "B?")
65–79%     Rated, Medium Confidence
≥ 80%      Rated, High Confidence
```

## Evidence source grades

| Grade | Sources | Use |
|---|---|---|
| **A** | company site, official careers page, official ATS, annual reports, regulatory filings, official engineering blog, official research/papers, official GitHub org, government & university pages | primary factual source |
| **B** | credible career rankings, LinkedIn company/employee movement, credible salary databases, mainstream news, university recruiting pages, industry research | supporting |
| **C** | Glassdoor, Reddit, Blind, anonymous reviews, scattered social media | **risk flags only** |

Every evidence row stores: `url`, `source_type`, `grade`, `fetched_at`,
`published_at`, `supports_dimension`, `summary`, `confidence`, `still_valid`.
