"""SAP SuccessFactors (Recruiting Marketing) career-site connector.

Generic across tenants — City of Toronto, Scotiabank and many Canadian public
and enterprise employers all run the same RMK career-site product, so this is
one connector rather than per-company scrapers.

Discovered by following each employer's official careers page to its vendor
(see scripts/discover_entry.py), not by guessing hostnames. Reads the same
public listing endpoint the site's own pagination calls.
"""

from __future__ import annotations

import html as htmllib
import re
from datetime import UTC, datetime
from urllib.parse import urljoin

from app.connectors._util import parse_dt
from app.connectors.base import Connector, ConnectorError, HttpLike, content_hash
from app.schemas.connector import ConnectorResult, RawJob, RawLocation, SourceConfig

PAGE_SIZE = 25          # the site returns its own page size; this bounds paging
MAX_PAGES = 20

# Capture the whole <li ...> INCLUDING its attributes: data-url lives there.
_TILE = re.compile(r'(<li[^>]*class="[^"]*job-tile[^"]*"[^>]*>.*?</li>)', re.S | re.I)
# RMK sites carry no location field; the city and province live in the URL slug,
# e.g. /job/Toronto-SENIOR-SYSTEMS-INTEGRATOR-ON-M5V-3C6/604575517/
_SLUG_LOCATION = re.compile(
    r"/job/([^/]+?)-([A-Z]{2})(?:-[A-Z0-9]{3}-?[A-Z0-9]{3})?/\d+/?$", re.I
)
_POSTAL_TAIL = re.compile(r"-[A-Z]{2}(-[A-Z0-9]{3}-?[A-Z0-9]{3})?$", re.I)
_JOB_ID = re.compile(r"job-id-(\d+)")
_DATA_URL = re.compile(r'data-url="([^"]+)"')
_TITLE = re.compile(r'class="jobTitle-link[^"]*"[^>]*>(.*?)</a>', re.S | re.I)
# section-field blocks carry label/value pairs (department, location, date...)
_FIELD = re.compile(
    r'class="section-field\s+([\w-]+)[^"]*"[^>]*>(.*?)(?=<div[^>]*class="section-field|\Z)',
    re.S | re.I,
)
_VALUE = re.compile(r'-value"[^>]*>(.*?)</div>', re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")


def _text(fragment: str) -> str:
    return " ".join(htmllib.unescape(_TAGS.sub(" ", fragment or "")).split())


def location_from_url(url: str) -> str:
    """Derive 'City, PROV' from an RMK job URL slug.

    These career sites expose no location field on the tile, but the slug is
    built as <City>-<TITLE>-<PROV>[-<POSTAL>]. Returns "" when the slug does not
    follow that shape — better empty than invented.
    """
    match = _SLUG_LOCATION.search(url or "")
    if not match:
        return ""
    slug, province = match.group(1), match.group(2).upper()
    city = htmllib.unescape(slug.split("-")[0]).replace("%20", " ").strip()
    if not city or not city[0].isalpha():
        return ""
    return f"{city}, {province}"


def parse_tiles(page_html: str, base_url: str, company: str | None) -> list[RawJob]:
    """Parse the RMK job tiles on one listing page."""
    jobs: list[RawJob] = []
    for raw_tile in _TILE.findall(page_html or ""):
        id_match = _JOB_ID.search(raw_tile)
        url_match = _DATA_URL.search(raw_tile)
        title_match = _TITLE.search(raw_tile)
        if not (id_match and title_match):
            continue

        job_id = id_match.group(1)
        title = _text(title_match.group(1))
        if not title:
            continue

        apply_url = urljoin(base_url, htmllib.unescape(url_match.group(1))) \
            if url_match else base_url

        fields: dict[str, str] = {}
        for kind, block in _FIELD.findall(raw_tile):
            value_match = _VALUE.search(block)
            value = _text(value_match.group(1)) if value_match else ""
            if value:
                fields[kind.lower()] = value

        location = (fields.get("location") or fields.get("city")
                    or location_from_url(apply_url))
        posted = fields.get("date") or fields.get("posteddate") or ""

        jobs.append(
            RawJob(
                source_job_id=job_id,
                title=title,
                company_name=company,
                department=fields.get("department"),
                employment_type=fields.get("type") or fields.get("employmenttype"),
                locations=[RawLocation(raw_text=location)] if location else [],
                official_source_url=apply_url,
                canonical_application_url=apply_url,
                source_posted_at=parse_dt(posted),
                source_status="open",
                content_hash=content_hash(title, location, job_id),
                raw={"fields": fields, "job_id": job_id},
            )
        )
    return jobs


class SuccessFactorsConnector(Connector):
    """``source.config``:

    base_url  -> career site root, e.g. https://jobs.toronto.ca/jobsatcity
    search    -> optional keyword filter applied server-side
    location  -> optional location filter applied server-side
    max_pages -> paging cap (default 20)
    """

    key = "successfactors"
    source_priority = 1

    @staticmethod
    def listing_url(base: str, startrow: int, search: str = "", location: str = "") -> str:
        return (
            f"{base.rstrip('/')}/tile-search-results/"
            f"?q={search}&location={location}&startrow={startrow}"
            f"&sortColumn=referencedate&sortDirection=desc"
        )

    async def fetch(self, source: SourceConfig, http: HttpLike, since=None) -> ConnectorResult:
        cfg = source.config
        base = cfg.get("base_url")
        if not base:
            raise ConnectorError("successfactors: config.base_url is required",
                                 stage="config", retryable=False)
        search = cfg.get("search", "")
        location = cfg.get("location", "")
        max_pages = int(cfg.get("max_pages", MAX_PAGES))
        # Resumable paging: callers may hand back the offset from a partial run.
        startrow = int(cfg.get("start_row", 0))

        collected: list[RawJob] = []
        seen: set[str] = set()
        page = 0
        completed = False

        while page < max_pages:
            url = self.listing_url(base, startrow, search, location)
            status, page_html, _ = await http.get_text(url)
            if status == 304 or not page_html:
                completed = True
                break

            batch = parse_tiles(page_html, base, cfg.get("company_name")
                                or source.display_name)
            fresh = [j for j in batch if j.source_job_id not in seen]
            for j in fresh:
                seen.add(j.source_job_id)
            collected.extend(fresh)

            if not fresh:
                completed = True
                break

            startrow += len(batch)
            page += 1
        else:
            completed = False

        return ConnectorResult(
            raw_jobs=collected,
            fetched_at=datetime.now(UTC),
            diagnostics={
                "pages_fetched": page,
                "next_start_row": startrow,     # resume point
                "sync_completed": completed,    # False => capped, more remain
                "collected": len(collected),
            },
        )
