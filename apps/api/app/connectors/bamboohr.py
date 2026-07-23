"""BambooHR connector — public careers list used by the employer's own page.

Discovered by following MaRS's official careers page to its ATS vendor rather
than guessing a domain.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.connectors.base import Connector, ConnectorError, HttpLike, content_hash
from app.schemas.connector import ConnectorResult, RawJob, RawLocation, SourceConfig


class BambooHrConnector(Connector):
    """``external_id`` is the BambooHR subdomain, e.g. "marsdd"."""

    key = "bamboohr"
    source_priority = 1

    @staticmethod
    def base_url(company: str) -> str:
        return f"https://{company}.bamboohr.com/careers/list"

    @staticmethod
    def job_url(company: str, job_id: str) -> str:
        return f"https://{company}.bamboohr.com/careers/{job_id}"

    async def fetch(self, source: SourceConfig, http: HttpLike, since=None) -> ConnectorResult:
        company = source.external_id
        status, body, _ = await http.get_json(self.base_url(company))
        if status == 304:
            return ConnectorResult(not_modified=True, fetched_at=datetime.now(UTC))
        if not isinstance(body, dict) or "result" not in body:
            raise ConnectorError("bamboohr: unexpected payload", stage="parse",
                                 retryable=False)

        raw_jobs: list[RawJob] = []
        for j in body.get("result") or []:
            job_id = str(j.get("id"))
            title = (j.get("jobOpeningName") or "").strip()
            loc = j.get("location") or {}
            parts = [loc.get("city"), loc.get("state"), loc.get("country")]
            loc_text = ", ".join(str(p) for p in parts if p)
            if j.get("isRemote") and not loc_text:
                loc_text = "Remote"
            url = self.job_url(company, job_id)

            raw_jobs.append(
                RawJob(
                    source_job_id=job_id,
                    title=title,
                    company_name=source.display_name,
                    department=(j.get("department") or {}).get("label")
                    if isinstance(j.get("department"), dict) else j.get("department"),
                    employment_type=j.get("employmentStatusLabel"),
                    remote_mode="remote" if j.get("isRemote") else None,
                    locations=[RawLocation(raw_text=loc_text)] if loc_text else [],
                    official_source_url=url,
                    canonical_application_url=url,
                    source_status="open",
                    content_hash=content_hash(title, loc_text, job_id),
                    raw=j,
                )
            )

        return ConnectorResult(raw_jobs=raw_jobs, fetched_at=datetime.now(UTC))
