"""SmartRecruiters connector — documented public postings API."""

from __future__ import annotations

from datetime import UTC, datetime

from app.connectors._util import parse_dt
from app.connectors.base import Connector, ConnectorError, HttpLike, content_hash
from app.schemas.connector import ConnectorResult, RawJob, RawLocation, SourceConfig

PAGE = 100
MAX_PAGES = 10


class SmartRecruitersConnector(Connector):
    """``external_id`` is the company identifier on SmartRecruiters."""

    key = "smartrecruiters"
    source_priority = 1

    @staticmethod
    def base_url(company: str, offset: int) -> str:
        return (
            f"https://api.smartrecruiters.com/v1/companies/{company}/postings"
            f"?limit={PAGE}&offset={offset}"
        )

    async def fetch(self, source: SourceConfig, http: HttpLike, since=None) -> ConnectorResult:
        raw_jobs: list[RawJob] = []
        for page in range(MAX_PAGES):
            url = self.base_url(source.external_id, page * PAGE)
            status, body, _ = await http.get_json(url)
            if status == 304:
                break
            if not isinstance(body, dict):
                raise ConnectorError("smartrecruiters: unexpected payload",
                                     stage="parse", retryable=False)
            content = body.get("content") or []
            if not content:
                break

            for j in content:
                loc = j.get("location") or {}
                parts = [loc.get("city"), loc.get("region"), loc.get("country")]
                loc_text = ", ".join(str(p) for p in parts if p)
                apply_url = (
                    j.get("applyUrl")
                    or f"https://jobs.smartrecruiters.com/{source.external_id}/{j.get('id')}"
                )
                title = (j.get("name") or "").strip()
                raw_jobs.append(
                    RawJob(
                        source_job_id=str(j.get("id")),
                        title=title,
                        company_name=(j.get("company") or {}).get("name"),
                        department=(j.get("department") or {}).get("label"),
                        employment_type=(j.get("typeOfEmployment") or {}).get("label"),
                        remote_mode="remote" if loc.get("remote") else None,
                        locations=[RawLocation(raw_text=loc_text)] if loc_text else [],
                        official_source_url=apply_url,
                        canonical_application_url=apply_url,
                        source_posted_at=parse_dt(j.get("releasedDate")),
                        source_status="open",
                        content_hash=content_hash(title, loc_text, str(j.get("id"))),
                        raw=j,
                    )
                )

            total = body.get("totalFound")
            if total is not None and (page + 1) * PAGE >= total:
                break

        return ConnectorResult(raw_jobs=raw_jobs, fetched_at=datetime.now(UTC))
