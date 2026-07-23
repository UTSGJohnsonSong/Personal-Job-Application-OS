"""Oracle Cloud Recruiting (the modern Taleo) connector.

Used by many public-sector employers, including several Canadian municipalities.
Reads the same public REST resource the employer's own careers page calls.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.connectors._util import parse_dt, strip_html
from app.connectors.base import Connector, ConnectorError, HttpLike, content_hash
from app.schemas.connector import ConnectorResult, RawJob, RawLocation, SourceConfig

PAGE = 50
MAX_PAGES = 8


class OracleOrcConnector(Connector):
    """``source.config``: host (tenant host), site (career site id, e.g. CX_1)."""

    key = "oracle_orc"
    source_priority = 1

    @staticmethod
    def base_url(host: str, site: str, offset: int) -> str:
        return (
            f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
            f"?onlyData=true&expand=requisitionList.secondaryLocations"
            f"&finder=findReqs;siteNumber={site},limit={PAGE},offset={offset}"
        )

    async def fetch(self, source: SourceConfig, http: HttpLike, since=None) -> ConnectorResult:
        cfg = source.config
        host = cfg.get("host")
        site = cfg.get("site", "CX_1")
        if not host:
            raise ConnectorError("oracle_orc: config.host is required", stage="config",
                                 retryable=False)

        raw_jobs: list[RawJob] = []
        for page in range(MAX_PAGES):
            url = self.base_url(host, site, page * PAGE)
            status, body, _ = await http.get_json(url)
            if status == 304 or not isinstance(body, dict):
                break

            items = body.get("items") or []
            requisitions: list[dict] = []
            for item in items:
                requisitions.extend(item.get("requisitionList") or [])
            if not requisitions:
                break

            for r in requisitions:
                rid = str(r.get("Id") or r.get("RequisitionId") or "")
                title = (r.get("Title") or "").strip()
                loc = r.get("PrimaryLocation") or r.get("Location")
                apply_url = f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{rid}"
                raw_jobs.append(
                    RawJob(
                        source_job_id=rid or title,
                        title=title,
                        company_name=cfg.get("company_name"),
                        description_text=strip_html(r.get("ExternalDescriptionStr")) or None,
                        locations=[RawLocation(raw_text=str(loc))] if loc else [],
                        official_source_url=apply_url,
                        canonical_application_url=apply_url,
                        source_posted_at=parse_dt(r.get("PostedDate")),
                        source_status="open",
                        content_hash=content_hash(title, str(loc), rid),
                        raw=r,
                    )
                )

            if len(requisitions) < PAGE:
                break

        return ConnectorResult(raw_jobs=raw_jobs, fetched_at=datetime.now(UTC))
