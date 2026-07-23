"""Sitemap-driven career-page connector.

Employers publish sitemap.xml so crawlers can find their job pages. This walks
the sitemap, keeps URLs that look like job pages, then extracts schema.org
JobPosting markup from each. Public pages only; bounded and polite.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from app.connectors.base import Connector, ConnectorError, HttpLike
from app.connectors.jsonld import _is_job_posting, _walk, extract_jsonld_blocks, job_from_jsonld
from app.schemas.connector import ConnectorResult, RawJob, SourceConfig

LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
DEFAULT_JOB_HINT = r"(job|career|posting|opening|vacanc|requisition)"
MAX_JOB_PAGES = 40


class SitemapCareerConnector(Connector):
    """``source.config``:

    sitemap_url -> the sitemap to walk
    job_pattern -> regex a URL must match to be treated as a job page
    max_pages   -> cap on job pages fetched (default 40)
    """

    key = "sitemap"
    source_priority = 1

    async def fetch(self, source: SourceConfig, http: HttpLike, since=None) -> ConnectorResult:
        cfg = source.config
        sitemap_url = cfg.get("sitemap_url")
        if not sitemap_url:
            raise ConnectorError("sitemap: config.sitemap_url is required",
                                 stage="config", retryable=False)
        pattern = re.compile(cfg.get("job_pattern", DEFAULT_JOB_HINT), re.I)
        cap = int(cfg.get("max_pages", MAX_JOB_PAGES))

        status, xml, _ = await http.get_text(sitemap_url)
        if status == 304 or not xml:
            return ConnectorResult(fetched_at=datetime.now(UTC), not_modified=True)

        urls = LOC_RE.findall(xml)
        # A sitemap index points at more sitemaps; follow one level only.
        nested = [u for u in urls if u.lower().endswith(".xml")][:5]
        for child in nested:
            try:
                _, child_xml, _ = await http.get_text(child)
                urls.extend(LOC_RE.findall(child_xml or ""))
            except Exception:
                continue  # one bad child sitemap must not abort the run

        job_urls = [u for u in dict.fromkeys(urls)
                    if not u.lower().endswith(".xml") and pattern.search(u)][:cap]

        raw_jobs: list[RawJob] = []
        for url in job_urls:
            try:
                _, html, _ = await http.get_text(url)
            except Exception:
                continue
            for block in extract_jsonld_blocks(html or ""):
                for node in _walk(block):
                    if _is_job_posting(node):
                        job = job_from_jsonld(node, page_url=url)
                        if job:
                            raw_jobs.append(job)

        return ConnectorResult(
            raw_jobs=raw_jobs, fetched_at=datetime.now(UTC),
            diagnostics={"sitemap_urls": len(urls), "job_pages": len(job_urls),
                         "postings": len(raw_jobs)},
        )
