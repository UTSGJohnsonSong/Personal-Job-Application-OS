from __future__ import annotations

from datetime import UTC, datetime

from app.connectors._util import parse_dt, strip_html
from app.connectors.base import Connector, ConnectorError, HttpLike, content_hash
from app.schemas.connector import ConnectorResult, RawJob, RawLocation, SourceConfig


class AshbyConnector(Connector):
    """First-party Ashby job board posting API."""

    key = "ashby"
    source_priority = 1

    def base_url(self, board: str) -> str:
        return (
            f"https://api.ashbyhq.com/posting-api/job-board/{board}"
            "?includeCompensation=true"
        )

    async def fetch(self, source: SourceConfig, http: HttpLike, since=None) -> ConnectorResult:
        url = self.base_url(source.external_id)
        status, body, resp_headers = await http.get_json(url)
        if status == 304:
            return ConnectorResult(not_modified=True, fetched_at=datetime.now(UTC))
        if not isinstance(body, dict) or "jobs" not in body:
            raise ConnectorError("ashby: unexpected payload", stage="parse", retryable=False)

        raw_jobs: list[RawJob] = []
        for j in body.get("jobs", []):
            desc = j.get("descriptionPlain") or strip_html(j.get("descriptionHtml"))
            loc = j.get("location")
            job_url = j.get("jobUrl")
            apply_url = j.get("applyUrl") or job_url
            remote = "remote" if j.get("isRemote") else None
            raw_jobs.append(
                RawJob(
                    source_job_id=str(j.get("id")),
                    title=(j.get("title") or "").strip(),
                    description_text=desc,
                    department=j.get("department") or j.get("team"),
                    employment_type=j.get("employmentType"),
                    remote_mode=remote,
                    locations=[RawLocation(raw_text=loc)] if loc else [],
                    official_source_url=job_url,
                    canonical_application_url=apply_url,
                    source_posted_at=parse_dt(j.get("publishedAt")),
                    source_updated_at=parse_dt(j.get("updatedAt")),
                    source_status="open",
                    content_hash=content_hash(j.get("title"), desc, loc),
                    raw=j,
                )
            )
        return ConnectorResult(
            raw_jobs=raw_jobs,
            etag=resp_headers.get("etag"),
            fetched_at=datetime.now(UTC),
        )
