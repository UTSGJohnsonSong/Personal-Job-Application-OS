"""Workday connector — the ATS behind most large enterprises and every big
Canadian bank, which is exactly where the candidate's target analyst roles live.

Uses the same public JSON endpoint the company's own public careers page calls
from the browser. Paged politely, with a hard cap, and every posting keeps its
official careers-site URL as the canonical application link.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.connectors._util import strip_html
from app.connectors.base import Connector, ConnectorError, HttpLike, content_hash
from app.schemas.connector import ConnectorResult, RawJob, RawLocation, SourceConfig

PAGE_SIZE = 20
MAX_PAGES = 10  # cap: never crawl an entire enterprise board in one pass


def _parse_posted(text: str | None) -> datetime | None:
    """Workday exposes relative strings like 'Posted 5 Days Ago'."""
    if not text:
        return None
    low = text.lower()
    now = datetime.now(UTC)
    if "today" in low:
        return now
    if "yesterday" in low:
        return now - timedelta(days=1)
    digits = "".join(c for c in low if c.isdigit())
    if not digits:
        return None
    n = int(digits)
    if "day" in low:
        return now - timedelta(days=n)
    if "week" in low:
        return now - timedelta(weeks=n)
    if "month" in low:
        return now - timedelta(days=30 * n)
    if "hour" in low:
        return now - timedelta(hours=n)
    return None


class WorkdayConnector(Connector):
    """First-party Workday careers site.

    ``source.config`` must provide:
        tenant  -> e.g. "rbc"
        wd      -> Workday pod number, e.g. 3
        site    -> career site id, e.g. "RBCEXTERNAL"
    """

    key = "workday"
    source_priority = 1

    @staticmethod
    def endpoint(tenant: str, wd: int, site: str) -> str:
        return (
            f"https://{tenant}.wd{wd}.myworkdayjobs.com"
            f"/wday/cxs/{tenant}/{site}/jobs"
        )

    @staticmethod
    def public_base(tenant: str, wd: int, site: str) -> str:
        return f"https://{tenant}.wd{wd}.myworkdayjobs.com/en-US/{site}"

    async def fetch(self, source: SourceConfig, http: HttpLike, since=None) -> ConnectorResult:
        cfg = source.config
        tenant = cfg.get("tenant") or source.external_id
        wd = int(cfg.get("wd", 3))
        site = cfg.get("site")
        if not site:
            raise ConnectorError("workday: config.site is required", stage="config",
                                 retryable=False)
        search = cfg.get("search", "")

        url = self.endpoint(tenant, wd, site)
        base = self.public_base(tenant, wd, site)
        raw_jobs: list[RawJob] = []
        seen: set[str] = set()

        for page in range(MAX_PAGES):
            body = {
                "appliedFacets": {},
                "limit": PAGE_SIZE,
                "offset": page * PAGE_SIZE,
                "searchText": search,
            }
            status, payload, _ = await http.post_json(url, json=body)
            if status == 304 or not isinstance(payload, dict):
                break
            postings = payload.get("jobPostings") or []
            if not postings:
                break

            for p in postings:
                path = p.get("externalPath") or ""
                job_id = p.get("bulletFields", [None])[0] or path
                if not job_id or job_id in seen:
                    continue
                seen.add(job_id)
                title = (p.get("title") or "").strip()
                loc = p.get("locationsText")
                apply_url = f"{base}{path}" if path else base
                raw_jobs.append(
                    RawJob(
                        source_job_id=str(job_id),
                        title=title,
                        company_name=cfg.get("company_name") or tenant,
                        description_text=strip_html(p.get("jobDescription")) or None,
                        locations=[RawLocation(raw_text=loc)] if loc else [],
                        official_source_url=apply_url,
                        canonical_application_url=apply_url,
                        source_posted_at=_parse_posted(p.get("postedOn")),
                        source_status="open",
                        content_hash=content_hash(title, loc, path),
                        raw=p,
                    )
                )

            total = payload.get("total")
            if total is not None and (page + 1) * PAGE_SIZE >= total:
                break

        return ConnectorResult(raw_jobs=raw_jobs, fetched_at=datetime.now(UTC))
