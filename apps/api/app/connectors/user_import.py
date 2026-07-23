"""User-import connector — for sources tied to the user's own account.

CLNx (UofT co-op), LinkedIn saved jobs and Indeed alert emails all sit behind a
personal login. Automating those accounts is an explicit non-goal
(docs/PRD.md §6, docs/SECURITY.md): the system never authenticates as the user
and never scrapes an authenticated session.

Instead the user supplies the content — pasted rows, an exported CSV, or a
forwarded alert email — and this connector parses it. Everything produced here
is DISCOVERY ONLY and must be resolved to the employer's official posting by
`app.ingestion.canonicalize` before it can be treated as applyable.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import UTC, datetime

from app.connectors.base import Connector, HttpLike, content_hash
from app.schemas.connector import ConnectorResult, RawJob, RawLocation, SourceConfig

URL_RE = re.compile(r"https?://[^\s<>\"')]+")

# "Title at Company" / "Title - Company" / "Title — Company"
TITLE_AT_COMPANY = re.compile(
    r"^\s*(?P<title>.+?)\s+(?:at|@|[-–—|])\s+(?P<company>[^|]+?)\s*$"
)


def _clean(text: str) -> str:
    return " ".join((text or "").split()).strip(" -–—|")


def parse_rows(text: str) -> list[dict]:
    """Parse pasted text.

    Supports CSV with headers, and one-posting-per-line free text such as
    'Data Analyst Intern at Acme  https://...'.
    """
    text = (text or "").strip()
    if not text:
        return []

    # CSV when the first line looks like a header row.
    first = text.splitlines()[0].lower()
    if "," in first and ("title" in first or "job" in first or "position" in first):
        rows: list[dict] = []
        for r in csv.DictReader(io.StringIO(text)):
            lowered = {(k or "").strip().lower(): (v or "").strip()
                       for k, v in r.items()}
            title = (lowered.get("title") or lowered.get("job title")
                     or lowered.get("position") or lowered.get("job"))
            if not title:
                continue
            rows.append({
                "title": title,
                "company": (lowered.get("company") or lowered.get("employer")
                            or lowered.get("organization")),
                "location": lowered.get("location") or lowered.get("city"),
                "url": lowered.get("url") or lowered.get("link"),
                "deadline": lowered.get("deadline") or lowered.get("closing date"),
            })
        return rows

    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        url_match = URL_RE.search(line)
        url = url_match.group(0) if url_match else None
        remainder = _clean(URL_RE.sub("", line))
        if not remainder and not url:
            continue
        title, company = remainder, None
        m = TITLE_AT_COMPANY.match(remainder)
        if m:
            title = _clean(m.group("title"))
            company = _clean(m.group("company"))
        if not title:
            continue
        out.append({"title": title, "company": company, "location": None,
                    "url": url, "deadline": None})
    return out


class UserImportConnector(Connector):
    """``source.config``:

    origin  -> uoft_clnx | linkedin | indeed_email | other   (provenance label)
    text    -> pasted CSV or free text supplied by the user
    """

    key = "user_import"
    # Discovery only: never first-party until canonicalization resolves it.
    source_priority = 3

    async def fetch(self, source: SourceConfig, http: HttpLike, since=None) -> ConnectorResult:
        origin = source.config.get("origin", "other")
        rows = parse_rows(source.config.get("text", ""))
        now = datetime.now(UTC)

        raw_jobs = [
            RawJob(
                source_job_id=content_hash(origin, r["title"], r.get("company"),
                                           r.get("url"))[:24],
                title=r["title"],
                company_name=r.get("company"),
                locations=([RawLocation(raw_text=r["location"])]
                           if r.get("location") else []),
                # The supplied link is DISCOVERY, not canonical. Canonicalization
                # decides what becomes canonical_application_url.
                official_source_url=None,
                canonical_application_url=None,
                source_status="unknown",
                content_hash=content_hash(origin, r["title"], r.get("company")),
                raw={"origin": origin, "discovery_url": r.get("url"),
                     "deadline_text": r.get("deadline"), "user_supplied": True},
            )
            for r in rows
        ]

        return ConnectorResult(
            raw_jobs=raw_jobs,
            fetched_at=now,
            diagnostics={"origin": origin, "rows": len(rows),
                         "note": "user-supplied; requires canonical resolution"},
        )
