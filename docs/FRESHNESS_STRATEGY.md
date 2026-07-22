# Freshness Strategy

## Timestamps per job
`first_seen_at`, `last_seen_at`, `source_posted_at`, `source_updated_at`,
`last_verified_at`, `application_deadline`, `source_status`, `current_status`,
`canonical_application_url`, `official_source_url`, `source_priority`,
`freshness_score`.

## Source status vs current status
- `source_status`: what the source last reported (`open`, `closed`, `removed`,
  `updated`, `reposted`, `unknown`).
- `current_status`: our derived truth after verification.
A job the official source no longer lists is set non-applyable even if an
aggregator still shows it.

## freshness_score (0..1)
Monotonic decay from `max(source_posted_at, last_verified_at)` combined with
verification recency and deadline proximity. Formula (deterministic, documented):
```
recency    = decay(now - last_verified_at, half_life=3d)
posting_age = decay(now - source_posted_at, half_life=21d)
deadline_boost = deadline within 72h ? +0.15 : 0
freshness = clamp(0.55*recency + 0.45*posting_age + deadline_boost, 0, 1)
```

## Re-verification cadence (idempotent jobs)
- High-volume sources: incremental sync on a fixed cadence.
- Target/hot companies: higher frequency.
- Jobs near deadline (<72h): verify more often.
- Closed jobs: back off frequency, keep archived.
- Use ETag / Last-Modified / content-hash to skip unchanged fetches.
- Per-source rate limit, retry, exponential backoff, circuit breaker.

## Transitions a re-verify can produce
still-open · closed · removed · updated · reposted · link-dead ·
only-third-party-still-shows. A closed/removed official posting → `current_status`
= `position_closed`, removed from applyable inbox, retained for history/learning.
