# Role Taxonomy

Roles are classified into four transferability bands. Classification **never**
relies on naive title substring matching.

## Bands

### R1 — Core Technical
`software_engineering`, `backend_engineering`, `data_engineering`,
`machine_learning_engineering`, `applied_ai`, `ml_infrastructure`,
`platform_engineering`, `cloud_engineering`

### R2 — High-Value Adjacent
`analytics_engineering`, `technical_product`, `ai_product`,
`product_engineering`, `technical_program_management`, `data_platform_analyst`,
`high_technical_product_analyst`

### R3 — Context-Dependent
`data_analyst`, `bi_analyst`, `business_systems_analyst`, `technology_analyst`,
`solutions_engineer`, `technical_project_management`, `general_product_analyst`

### R4 — Low Transferability
`sales`, `customer_support`, `hr`, `general_marketing`,
`nontechnical_operations`, `administrative`, `nontechnical_business_development`

## Why substring matching is banned

`"engineer" in title` misclassifies **Sales Engineer**, **Solutions Engineer**,
**Field Engineer** and **Support Engineer** as core technical roles. The
classifier therefore uses:

1. **Negative title signals first** — `sales engineer`, `solutions engineer`,
   `field engineer`, `support engineer`, `account …` route to R3/R4 regardless
   of the word "engineer".
2. **Title phrase matching** on normalized, tokenized titles (word-boundary,
   not substring).
3. **Body signals** — responsibilities, required skills, deliverables, team,
   tools, domain, seniority — which can confirm or *demote* a title-based guess.

A title-only classification is capped at `confidence = 0.55` and records
`needs_review = true` when body evidence is absent.

## Transferability coefficient

Used to damp the company-platform bonus for weak roles:

```
R1 = 1.0
R2 = 0.9
R3 = 0.7–0.9  (by technical content actually evidenced in the JD)
R4 = 0.0–0.2
```

This encodes the product rule: **platform is king, but the role must clear a
floor.** An S-tier pure sales role never outranks a B-tier backend role.

## Every classification stores

`category` (R1–R4), `role_type`, `confidence`, `evidence[]` (the JD spans that
drove it), `signals_positive`, `signals_negative`, `needs_review`.

LLM may propose a category + evidence, but the output passes strict schema
validation and the final mapping is rule-governed.
