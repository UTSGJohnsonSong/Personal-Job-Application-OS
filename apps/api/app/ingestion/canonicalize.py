"""Canonicalization: third-party discovery -> the employer's own posting.

Required flow for anything found on an aggregator or community board:

    third-party posting
      -> find the employer's official site
      -> find their official ATS board
      -> verify the posting is still open there
      -> official URL becomes canonical_application_url
      -> the third-party link is retained ONLY as a discovery source

The third-party link is never the source of truth, and is never silently
promoted to canonical. When resolution fails we say so and keep the posting
flagged, rather than pretending the aggregator link is official.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import urlparse

from app.connectors.base import HttpLike
from app.ingestion.normalize import normalize_company, title_core

# Host patterns that identify an employer's own applicant tracking system.
ATS_HOST_PATTERNS: list[tuple[str, str]] = [
    (r"boards\.greenhouse\.io|job-boards\.greenhouse\.io", "greenhouse"),
    (r"jobs\.lever\.co", "lever"),
    (r"jobs\.ashbyhq\.com", "ashby"),
    (r"jobs\.smartrecruiters\.com|careers\.smartrecruiters\.com", "smartrecruiters"),
    (r"myworkdayjobs\.com", "workday"),
    (r"\.icims\.com", "icims"),
    (r"taleo\.net|oraclecloud\.com", "taleo_orc"),
    (r"successfactors\.com|sapsf\.com", "successfactors"),
    (r"bamboohr\.com", "bamboohr"),
    (r"jobvite\.com", "jobvite"),
    (r"workable\.com", "workable"),
    (r"breezy\.hr", "breezy"),
    (r"recruitee\.com", "recruitee"),
]

# Hosts that are never canonical — discovery only.
AGGREGATOR_HOSTS = re.compile(
    r"(linkedin\.com|indeed\.|glassdoor\.|wellfound\.com|angel\.co|ziprecruiter\.|"
    r"simplify\.jobs|builtin\.|monster\.|jobbank\.gc\.ca|talent\.com|jooble\.)",
    re.I,
)


class ResolutionStatus(StrEnum):
    ALREADY_CANONICAL = "already_canonical"
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    CLOSED_AT_SOURCE = "closed_at_source"
    CONFLICT = "conflict"


@dataclass
class ResolutionResult:
    status: ResolutionStatus
    canonical_url: str | None = None
    ats_kind: str | None = None
    discovery_url: str | None = None
    employer_domain: str | None = None
    verified_open: bool | None = None
    checked_at: datetime | None = None
    evidence: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def usable_as_canonical(self) -> bool:
        return self.status in (
            ResolutionStatus.ALREADY_CANONICAL, ResolutionStatus.RESOLVED
        ) and bool(self.canonical_url)


def identify_ats(url: str | None) -> str | None:
    """Return the ATS kind if the URL is already an employer's own board."""
    if not url:
        return None
    host = (urlparse(url).netloc or "").lower()
    for pattern, kind in ATS_HOST_PATTERNS:
        if re.search(pattern, host):
            return kind
    return None


def is_aggregator(url: str | None) -> bool:
    if not url:
        return False
    return bool(AGGREGATOR_HOSTS.search(urlparse(url).netloc or ""))


def titles_match(a: str | None, b: str | None) -> bool:
    """Loose title comparison used to confirm we resolved to the SAME job."""
    ca, cb = title_core(a), title_core(b)
    if not ca or not cb:
        return False
    if ca == cb:
        return True
    ta, tb = set(ca.split()), set(cb.split())
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / min(len(ta), len(tb))
    return overlap >= 0.7


async def resolve(
    *,
    discovery_url: str | None,
    title: str,
    company_name: str | None,
    http: HttpLike,
    candidate_boards: list[tuple[str, str]] | None = None,
) -> ResolutionResult:
    """Resolve a discovered posting to the employer's official posting.

    `candidate_boards` is an optional list of (connector_key, external_id) the
    caller already knows for this employer (e.g. from the company record), which
    avoids guessing.
    """
    now = datetime.now(UTC)

    # 1) Already on an employer ATS? Then it is canonical as-is.
    kind = identify_ats(discovery_url)
    if kind and not is_aggregator(discovery_url):
        return ResolutionResult(
            status=ResolutionStatus.ALREADY_CANONICAL,
            canonical_url=discovery_url, ats_kind=kind,
            discovery_url=discovery_url, checked_at=now,
            evidence=[f"host matches known ATS: {kind}"],
        )

    result = ResolutionResult(
        status=ResolutionStatus.UNRESOLVED,
        discovery_url=discovery_url, checked_at=now,
    )
    if is_aggregator(discovery_url):
        result.evidence.append("discovery link is an aggregator; not canonical")

    if not company_name:
        result.problems.append("no employer name on the third-party posting")
        return result

    # 2) Search the employer's known official boards for the same title.
    from app.connectors.registry import get_connector
    from app.schemas.connector import SourceConfig

    for connector_key, external_id in (candidate_boards or []):
        try:
            conn = get_connector(connector_key)
        except KeyError:
            continue
        try:
            res = await conn.fetch(
                SourceConfig(connector_key=connector_key, external_id=external_id,
                             display_name=company_name),
                http,
            )
        except Exception as exc:  # a failing board must not abort resolution
            result.problems.append(f"{connector_key}:{external_id} fetch failed: {exc}")
            continue

        for job in res.raw_jobs:
            if titles_match(job.title, title):
                url = job.canonical_application_url or job.official_source_url
                result.status = ResolutionStatus.RESOLVED
                result.canonical_url = url
                result.ats_kind = connector_key
                result.verified_open = job.source_status == "open"
                result.employer_domain = (urlparse(url).netloc if url else None)
                result.evidence.append(
                    f"matched '{job.title}' on {connector_key}:{external_id}"
                )
                if not result.verified_open:
                    result.status = ResolutionStatus.CLOSED_AT_SOURCE
                    result.problems.append(
                        "found on the official board but it is no longer open"
                    )
                return result

        result.evidence.append(
            f"searched {connector_key}:{external_id} ({len(res.raw_jobs)} postings), no title match"
        )

    if not candidate_boards:
        result.problems.append(
            "no official board known for this employer — run company research first"
        )
    else:
        result.problems.append(
            "title not found on any known official board; posting may be closed, "
            "renamed, or exclusive to the third-party site"
        )
    return result


def apply_resolution(job_fields: dict, res: ResolutionResult) -> dict:
    """Apply a resolution to job fields.

    The aggregator link is demoted to `discovery_url` and NEVER written to
    canonical_application_url.
    """
    out = dict(job_fields)
    out["discovery_url"] = res.discovery_url
    out["canonical_resolution_status"] = res.status.value

    if res.usable_as_canonical:
        out["canonical_application_url"] = res.canonical_url
        out["official_source_url"] = res.canonical_url
        out["source_priority"] = 1
    else:
        # Refuse to promote a third-party link. Keep the job, flag it clearly.
        out["canonical_application_url"] = None
        out["official_source_url"] = None
        out["source_priority"] = 3
        out["inbox_category"] = "manual_review"
        if res.status is ResolutionStatus.CLOSED_AT_SOURCE:
            out["source_status"] = "closed"
            out["current_status"] = "position_closed"
    return out


def company_key(name: str | None) -> str:
    return normalize_company(name)
