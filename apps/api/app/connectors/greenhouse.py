from __future__ import annotations

from datetime import UTC, datetime

from app.connectors._util import parse_dt, strip_html
from app.connectors.base import Connector, ConnectorError, HttpLike, content_hash
from app.schemas.connector import ConnectorResult, RawJob, RawLocation, SourceConfig


class GreenhouseConnector(Connector):
    """First-party Greenhouse job board (the company's own hosted board)."""

    key = "greenhouse"
    source_priority = 1

    def base_url(self, board: str) -> str:
        return f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"

    async def fetch(self, source: SourceConfig, http: HttpLike, since=None) -> ConnectorResult:
        url = self.base_url(source.external_id)
        headers = {}
        if source.etag:
            headers["If-None-Match"] = source.etag
        status, body, resp_headers = await http.get_json(url, headers=headers)
        if status == 304:
            return ConnectorResult(not_modified=True, fetched_at=datetime.now(UTC))
        if not isinstance(body, dict) or "jobs" not in body:
            raise ConnectorError("greenhouse: unexpected payload", stage="parse", retryable=False)

        raw_jobs: list[RawJob] = []
        for j in body.get("jobs", []):
            desc = strip_html(j.get("content"))
            loc = (j.get("location") or {}).get("name")
            url_abs = j.get("absolute_url")
            raw_jobs.append(
                RawJob(
                    source_job_id=str(j.get("id")),
                    title=(j.get("title") or "").strip(),
                    description_text=desc,
                    department=", ".join(
                        d.get("name", "") for d in (j.get("departments") or [])
                    )
                    or None,
                    locations=[RawLocation(raw_text=loc)] if loc else [],
                    official_source_url=url_abs,
                    canonical_application_url=url_abs,
                    source_updated_at=parse_dt(j.get("updated_at")),
                    source_status="open",
                    content_hash=content_hash(j.get("title"), desc, loc),
                    raw=j,
                )
            )
        return ConnectorResult(
            raw_jobs=raw_jobs,
            etag=resp_headers.get("etag"),
            last_modified=resp_headers.get("last-modified"),
            fetched_at=datetime.now(UTC),
        )
