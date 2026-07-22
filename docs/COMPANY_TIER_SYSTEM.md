# Company Tier System

A company is **not** one number on one axis. Each company carries seven
independent ratings, each produced from graded evidence, each bounded by
Evidence Coverage.

## The seven tiers

| Tier | Question it answers |
|---|---|
| `global_brand_tier` | Résumé recognition worldwide; signal to any future recruiter |
| `canada_market_tier` | Hiring presence in Canada/Toronto; local recruiter recognition; UofT pipeline |
| `technical_domain_tier` | Technical standing in AI / SW / data / cloud / silicon / AV / fintech |
| `internship_program_tier` | Real student program: mentors, real projects, return-offer path |
| `career_optionality_tier` | How many high-value directions open up afterwards |
| `stability_tier` | Funding/operating health; risk the role or program is cancelled |
| `overall_personal_tier` | **Not a public fact** — strategic value *to this user at this stage* |

A company may legitimately be `Global Brand: B` and `AI Domain: S`
simultaneously (e.g. a domain-elite AV startup). That is not a contradiction —
it is the point of having multiple axes.

## Company types

- **Global Platform** — huge brand + optionality.
- **Domain Elite** — small, but top-tier technical density in a target domain.
- **Canada Platform** — high value in the local market / banking / enterprise / campus hiring.

The system must never downgrade a company to "ordinary small company" merely
because it lacks global consumer fame.

## Company Platform Score (0–100)

Sub-dimensions and v1 default weights:

| Sub-dimension | Weight |
|---|---|
| Resume / Brand Signal | 30% |
| Technical Density | 20% |
| Internship Program Quality | 15% |
| Career Optionality | 15% |
| System / Project Scale | 10% |
| Talent Network | 5% |
| Stability | 5% |

## Tier bands

```
S: 88–100   platform alone materially changes the next job search
A: 76–87    strong brand, technical or industry platform
B: 62–75    reliable, real résumé and growth value
C: 45–61    ordinary; value determined by the specific role and team
D:  0–44    weak platform, high risk, or little career gain
```

## Tiers are bounded by Evidence Coverage

A score is never presented as a settled tier unless the evidence supports it.
See `EVIDENCE_COVERAGE.md`. Display `B?` / `Provisional` rather than `B` when
coverage is insufficient.

## Formal S-tier requirements

1. ≥ 2 independent evidence types, **and**
2. ≥ 1 Grade-A source, **and**
3. Evidence Coverage ≥ 0.80.

Grade-C (anonymous) evidence alone can never promote to S nor demote to D — it
may only raise risk flags.

## Overrides

`company_personal_overrides` stores the user's manual tier separately from the
system's evidence-derived tier. The system tier is never silently overwritten,
and an override always records a reason. **Adding an override requires explicit
user confirmation.**
