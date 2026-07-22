# Internship Ranking Mode

> **Core product principle:** in Internship Mode, platform value outranks perfect
> current fit — but platform cannot rescue a role with no technical, data,
> product, engineering or project-management transferability.
> *平台为王，岗位必须过底线。*

## The pipeline (eligibility is a gate, not a score)

```
Eligibility Gate  →  PASS / REVIEW / FAIL
     FAIL   → excluded from the normal priority queue
     REVIEW → Manual Review queue
     PASS   → continue to scoring
                ↓
   six independent scores (never merged into one "match %")
                ↓
   Tier × Role interaction rules + platform multiplier
                ↓
   Application Priority (0–100)  +  Urgency / Effort ordering
```

Eligibility is **removed** from the weighted sum entirely. Being allowed to
apply is not evidence that the job is a good fit.

## Six reported scores

1. **Company Platform Value** — value of the company as an internship platform
2. **Role Strategic Value** — transferable value of the role itself
3. **Current Candidate Fit** — how well the user's evidenced experience matches
4. **Team / Project Quality** — is the actual work real and tellable
5. **Career Optionality** — how many directions open afterwards
6. **Overall Application Priority** — the ordering decision

Plus: **Evidence Coverage**, **Freshness/Urgency**, **Application Effort**,
**Opportunity Estimate**.

## Internship Mode default weights

| Component | Weight |
|---|---|
| Company Platform Value | 50% |
| Role Strategic Value | 20% |
| Team / Project Quality | 12% |
| Current Candidate Fit | 10% |
| Opportunity Estimate | 5% |
| Freshness + Effort | 3% |

Rationale: at internship stage the platform is the dominant strategic variable.
The user should not miss a high-value platform because they don't yet know a few
tools listed in the JD.

## Tier × Role interaction rules

```
S + R1 → Serious Apply
S + R2 → Serious Apply
S + R3 → Serious Apply or High-Priority Review   (may outrank B/C + R1)
A + R1 → Serious Apply
A + R2 → Serious Apply or High-Priority Review
B/C + R1 → competes on team quality, role strategic value, concrete evidence
any + R4 → platform bonus heavily damped
```

## Platform multiplier (non-linear)

```
S = 1.18   A = 1.10   B = 1.04   C = 1.00   D = 0.85
effective_bonus = (multiplier − 1) × transferability_coefficient
```

R4's coefficient (0–0.2) is what stops an S-tier sales role from dominating.

## Freshness and Application Cost

They never increase strategic value. They only affect **when** and **how**:

```
Strategic Value   → is it worth applying at all
Freshness/Deadline→ is it worth applying right now
Application Cost  → Quick Apply / Serious Apply / Manual
```

A brand-new bad job is still a bad job. A 2-minute bad job is still a bad job.
A high-value job stays high-value even if the form is long.

## Opportunity Estimate

With no real outcome history, report:

```
Opportunity Estimate: Insufficient Personal Outcome Data
```

Never default to `0.5 / confidence 0.3`. Future learning tracks reply,
assessment, interview, offer and *final user interest* separately — optimizing
reply rate alone would favour easy low-value jobs.

## Ranking modes

`internship` (default) · `new_grad` · `experienced`. The 50% company weight is
specific to Internship Mode and must not be reused for the others.
