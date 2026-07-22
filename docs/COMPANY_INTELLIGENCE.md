# Company Intelligence

## Hard rule: tiers are never produced from model impressions

Forbidden:
```
Amazon is famous          → S Tier
Waabi is a startup        → B Tier
RBC is a bank             → A Tier
```

The only legitimate path is:

```
external evidence collection
  → structured fact extraction
  → source-grade assessment
  → transparent scoring
  → evidence coverage
  → system tier
  → (optional, user-confirmed) personal override
```

An LLM may **extract facts, summarize evidence, categorize, flag uncertainty and
write the natural-language explanation**. An LLM may **not** emit a final tier or
an unsourced 0–100 score.

## Company Research Pipeline

Runs in the background for any unknown company:

1. Confirm official domain and legal entity
2. Locate official About + Careers pages
3. Confirm the product/business actually exists
4. Check Canada / Toronto presence
5. Check official engineering blog, papers, GitHub org
6. Check for a formal internship program
7. Check size, funding, annual report or regulatory filings
8. Check external career signal / hiring-market recognition
9. Produce a **Company Evidence Card**
10. Compute sub-scores, coverage, provisional tier

## Failure handling

Research failure must never be silent. On failure the company is marked
`needs_research`, the failure reason is retained, and the job is retried. The
system must **never** fill gaps with unsourced guesses — an unknown dimension
stays `score=null, confidence=0`.

## Bootstrap records

Well-known companies may get a bootstrap record to avoid a cold start, but a
bootstrap is explicitly marked as such, carries its own (low) coverage, and is
**not** treated as permanent truth. It must be replaced by collected evidence.

## Stored per company

```
score_version, evidence_sources, last_reviewed_at, evidence_coverage,
system_tier, personal_tier, manual_override, personal_override, override_reason
```

Adding a personal override requires explicit user confirmation.
