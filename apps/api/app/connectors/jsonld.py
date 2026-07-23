"""Generic career-page connector using schema.org/JobPosting (JSON-LD).

Employers publish JSON-LD so search engines can index their jobs; reading it is
the intended use of that markup. One connector therefore unlocks many employers,
government sites and community boards at once, without bespoke HTML scraping.

Only public pages are read. Nothing here logs in or bypasses access control.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from app.connectors._util import parse_dt, strip_html
from app.connectors.base import Connector, ConnectorError, HttpLike, content_hash
from app.schemas.connector import ConnectorResult, RawJob, RawLocation, SourceConfig

_LD_BLOCK = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)


def extract_jsonld_blocks(html: str) -> list[Any]:
    """Return every parsed JSON-LD block; malformed blocks are skipped."""
    out: list[Any] = []
    for raw in _LD_BLOCK.findall(html or ""):
        text = raw.strip()
        if not text:
            continue
        try:
            out.append(json.loads(text))
        except json.JSONDecodeError:
            # Some sites emit trailing commas or concatenated objects.
            cleaned = re.sub(r",\s*([}\]])", r"\1", text)
            try:
                out.append(json.loads(cleaned))
            except json.JSONDecodeError:
                continue
    return out


def _walk(node: Any):
    """Yield every dict in a nested JSON-LD structure (handles @graph, lists)."""
    if isinstance(node, dict):
        yield node
        for key in ("@graph", "itemListElement", "mainEntity"):
            if key in node:
                yield from _walk(node[key])
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _is_job_posting(node: dict) -> bool:
    t = node.get("@type")
    if isinstance(t, list):
        return any(str(x).lower() == "jobposting" for x in t)
    return str(t).lower() == "jobposting"


def _location_texts(node: dict) -> list[str]:
    locs: list[str] = []
    raw = node.get("jobLocation")
    for item in raw if isinstance(raw, list) else [raw]:
        if not isinstance(item, dict):
            if isinstance(item, str):
                locs.append(item)
            continue
        addr = item.get("address")
        if isinstance(addr, dict):
            parts = [
                addr.get("addressLocality"),
                addr.get("addressRegion"),
                addr.get("addressCountry") if isinstance(addr.get("addressCountry"), str)
                else (addr.get("addressCountry") or {}).get("name"),
            ]
            text = ", ".join(str(p) for p in parts if p)
            if text:
                locs.append(text)
        elif isinstance(addr, str):
            locs.append(addr)
    if node.get("jobLocationType") == "TELECOMMUTE" and not locs:
        locs.append("Remote")
    return locs


def job_from_jsonld(node: dict, *, page_url: str | None) -> RawJob | None:
    """Map one schema.org JobPosting to a RawJob."""
    title = (node.get("title") or "").strip()
    if not title:
        return None

    org = node.get("hiringOrganization")
    company = None
    if isinstance(org, dict):
        company = org.get("name")
    elif isinstance(org, str):
        company = org

    apply_url = node.get("url") or page_url
    identifier = node.get("identifier")
    if isinstance(identifier, dict):
        identifier = identifier.get("value")
    job_id = str(identifier or apply_url or title)

    desc = strip_html(node.get("description"))
    locs = _location_texts(node)
    employment = node.get("employmentType")
    if isinstance(employment, list):
        employment = ", ".join(str(e) for e in employment)

    return RawJob(
        source_job_id=job_id,
        title=title,
        company_name=company,
        description_text=desc or None,
        employment_type=str(employment) if employment else None,
        remote_mode="remote" if node.get("jobLocationType") == "TELECOMMUTE" else None,
        locations=[RawLocation(raw_text=x) for x in locs],
        official_source_url=apply_url,
        canonical_application_url=apply_url,
        source_posted_at=parse_dt(node.get("datePosted")),
        source_updated_at=parse_dt(node.get("dateModified")),
        source_status="open",
        content_hash=content_hash(title, desc, ",".join(locs)),
        raw={"jsonld": node},
    )


class JsonLdCareerConnector(Connector):
    """Reads schema.org JobPosting markup from one or more public pages.

    ``source.config``:
        urls        -> list of pages to read (listing pages or job pages)
        max_pages   -> safety cap (default 25)
    """

    key = "jsonld"
    source_priority = 1

    async def fetch(self, source: SourceConfig, http: HttpLike, since=None) -> ConnectorResult:
        urls = source.config.get("urls") or []
        if isinstance(urls, str):
            urls = [urls]
        if not urls:
            raise ConnectorError("jsonld: config.urls is required", stage="config",
                                 retryable=False)
        cap = int(source.config.get("max_pages", 25))

        raw_jobs: list[RawJob] = []
        diagnostics: dict = {"pages": 0, "blocks": 0, "postings": 0}

        for url in urls[:cap]:
            status, html, _ = await http.get_text(url)
            if status == 304 or not html:
                continue
            diagnostics["pages"] += 1
            for block in extract_jsonld_blocks(html):
                diagnostics["blocks"] += 1
                for node in _walk(block):
                    if not _is_job_posting(node):
                        continue
                    job = job_from_jsonld(node, page_url=url)
                    if job:
                        raw_jobs.append(job)
                        diagnostics["postings"] += 1

        return ConnectorResult(
            raw_jobs=raw_jobs, fetched_at=datetime.now(UTC), diagnostics=diagnostics
        )
