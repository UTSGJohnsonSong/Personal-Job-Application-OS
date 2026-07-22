# Job Sources

## Priority ladder
1. **Company official ATS** — Greenhouse, Lever, Ashby, Workday, SmartRecruiters,
   iCIMS, SuccessFactors, Taleo, BambooHR, Jobvite, and official Careers pages.
2. **Government / university / institutional** — Canada Job Bank, gov portals,
   university career portals, hospitals/research/non-profits, official company
   GitHub/announcements.
3. **Aggregators** — LinkedIn, Indeed, Glassdoor, Wellfound, Built In, Simplify.
   Used for discovery only; always trace back to the official job page and set it
   as the `canonical_application_url`. Never treat an aggregator as the sole truth.

## First-party APIs used in v1 (public, documented, no auth)
- **Greenhouse**: `https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true`
- **Lever**: `https://api.lever.co/v0/postings/{company}?mode=json`
- **Ashby**: `https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true`

These are the companies' own hosted job boards — first-party, canonical, and the
`hostedUrl` / `absolute_url` they return is the official application URL.

## Canonicalization
Each job stores both `official_source_url` and `canonical_application_url`.
When discovered via an aggregator, we resolve to the ATS URL and mark the ATS as
canonical; the aggregator is retained as an additional `source` in the job's
duplicate group, not lost.

## Source metadata every connector must provide
`source_priority`, `official_source_url`, `canonical_application_url`,
`source_job_id`, `source_posted_at`, `source_updated_at`, `source_status`.

## Adding a source
New sources implement the `Connector` interface (see CONNECTOR_INTERFACE.md) and
register via entry-point/registry — **no core business-logic change required**.
