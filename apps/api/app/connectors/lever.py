from __future__ import annotations

from datetime import UTC, datetime

from app.connectors._util import parse_dt, strip_html
from app.connectors.base import Connector, ConnectorError, HttpLike, content_hash
from app.schemas.connector import ConnectorResult, RawJob, RawLocation, SourceConfig

_REMOTE_MAP = {"remote": "remote", "on-site": "onsite", "hybrid": "hybrid"}


class LeverConnector(Connector):
    """First-party Lever postings for a company."""

    key = "lever"
    source_priority = 1

    def base_url(self, company: str) -> str:
        return f"https://api.lever.co/v0/postings/{company}?mode=json"

    async def fetch(self, source: SourceConfig, http: HttpLike, since=None) -> ConnectorResult:
        url = self.base_url(source.external_id)
        status, body, resp_headers = await http.get_json(url)
        if status == 304:
            return ConnectorResult(not_modified=True, fetched_at=datetime.now(UTC))
        if not isinstance(body, list):
            raise ConnectorError("lever: expected list payload", stage="parse", retryable=False)

        raw_jobs: list[RawJob] = []
        for j in body:
            cats = j.get("categories") or {}
            desc = j.get("descriptionPlain") or strip_html(j.get("description"))
            loc = cats.get("location")
            hosted = j.get("hostedUrl")
            apply_url = j.get("applyUrl") or hosted
            workplace = (j.get("workplaceType") or "").lower()
            raw_jobs.append(
                RawJob(
                    source_job_id=str(j.get("id")),
                    title=(j.get("text") or "").strip(),
                    description_text=desc,
                    department=cats.get("team") or cats.get("department"),
                    employment_type=cats.get("commitment"),
                    remote_mode=_REMOTE_MAP.get(workplace),
                    locations=[RawLocation(raw_text=loc)] if loc else [],
                    official_source_url=hosted,
                    canonical_application_url=apply_url,
                    source_posted_at=parse_dt(j.get("createdAt")),
                    source_status="open",
                    content_hash=content_hash(j.get("text"), desc, loc),
                    raw=j,
                )
            )
        return ConnectorResult(
            raw_jobs=raw_jobs,
            etag=resp_headers.get("etag"),
            fetched_at=datetime.now(UTC),
        )
