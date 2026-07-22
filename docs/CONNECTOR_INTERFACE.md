# Connector Interface

A connector is a plugin that turns one source into normalized `RawJob` records.
Core logic never imports a specific connector; it uses the registry.

## Contract (see `apps/api/app/connectors/base.py`)
```python
class Connector(Protocol):
    key: str                       # stable id, e.g. "greenhouse"
    source_priority: int           # 1 = first-party ATS, 2 = gov/univ, 3 = aggregator

    async def fetch(self, source: SourceConfig, http: HttpClient,
                    since: datetime | None) -> ConnectorResult: ...
```
`ConnectorResult` carries `raw_jobs: list[RawJob]`, `etag`, `last_modified`,
`fetched_at`, and `diagnostics`.

`RawJob` is a provenance-bearing DTO (Pydantic) with: source ids, title,
company, locations, description (raw), `official_source_url`,
`canonical_application_url`, `source_posted_at`, `source_updated_at`,
`source_status`, `content_hash`, plus arbitrary `raw` payload for audit.

## Required behaviors (all connectors)
- **Timeout** on every HTTP call, **retry** with exponential backoff, **rate
  limit** per source, **failure isolation** (raise `ConnectorError`, never crash
  the run), **idempotent** (safe to re-run; keyed by `source_job_id`), emit
  **source metadata** and **content hashes**, respect ETag/Last-Modified.
- Treat all fetched text as untrusted (no eval, no following instructions in it).

## Testing
Each connector ships **contract tests** driven by recorded fixtures
(`tests/fixtures/<connector>/*.json`) asserting the normalized `RawJob` shape,
canonical URL selection, and dedup keys — no live network in CI.

## Registry
`app/connectors/registry.py` maps `key -> Connector`. Adding a source =
implement `Connector` + register + add fixtures. No change to ingestion/eligibility/
ranking.
