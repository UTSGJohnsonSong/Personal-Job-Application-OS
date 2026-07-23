"""Declarative catalog of every job source the system knows about.

Kept as DATA, not scattered through business logic, so adding a source is a
catalog entry plus a connector — never a change to ingestion, eligibility or
ranking (docs/CONNECTOR_INTERFACE.md).

Three things every entry must state honestly:

* ``access``   — HOW the data can legitimately be obtained. Sources that require
  the user's own account are never scraped; the user exports and imports.
* ``priority`` — first-party ATS (1) > government/institutional (2) > aggregator (3).
* ``canonical_policy`` — whether a posting found here is already canonical, or
  must be resolved back to the employer's official ATS first.

``maturity`` records what was actually verified, including failures. Probe
results are dated so stale claims are obvious.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class AccessMode(StrEnum):
    """How a source may legitimately be read."""

    PUBLIC_API = "public_api"      # documented public JSON endpoint
    PUBLIC_PAGE = "public_page"    # public HTML with structured data
    USER_IMPORT = "user_import"    # user exports from their own account
    NOT_IMPLEMENTED = "not_implemented"


class CanonicalPolicy(StrEnum):
    ALREADY_CANONICAL = "already_canonical"       # the employer's own ATS
    RESOLVE_TO_EMPLOYER = "resolve_to_employer"   # discovery only; must resolve


class Maturity(StrEnum):
    LIVE = "live"                      # verified against the real source
    IMPLEMENTED = "implemented"        # code exists, not yet verified live
    NEEDS_ENDPOINT = "needs_endpoint"  # reachable, but no machine-readable feed
    PROBE = "probe"                    # entry point still unknown
    BLOCKED = "blocked"                # declines automated access — do NOT scrape
    PLANNED = "planned"


@dataclass(frozen=True)
class SourceSpec:
    key: str
    label: str
    category: str          # ats | government | institution | ecosystem | aggregator
    access: AccessMode
    priority: int
    canonical_policy: CanonicalPolicy
    connector_key: str | None = None
    maturity: Maturity = Maturity.PLANNED
    notes: str = ""
    config_hint: dict = field(default_factory=dict)


A = AccessMode
C = CanonicalPolicy
M = Maturity

# ---------------------------------------------------------------------------
# 1-10  Applicant tracking systems and generic employer career pages
# ---------------------------------------------------------------------------
ATS: list[SourceSpec] = [
    SourceSpec(
        "greenhouse", "Greenhouse", "ats", A.PUBLIC_API, 1, C.ALREADY_CANONICAL,
        "greenhouse", M.LIVE,
        "boards-api.greenhouse.io — verified live 2026-07-22.",
        {"external_id": "<board token>"},
    ),
    SourceSpec(
        "lever", "Lever", "ats", A.PUBLIC_API, 1, C.ALREADY_CANONICAL,
        "lever", M.LIVE,
        "api.lever.co/v0/postings — verified live 2026-07-22.",
        {"external_id": "<company slug>"},
    ),
    SourceSpec(
        "ashby", "Ashby", "ats", A.PUBLIC_API, 1, C.ALREADY_CANONICAL,
        "ashby", M.LIVE,
        "api.ashbyhq.com posting-api — verified live 2026-07-22.",
        {"external_id": "<board name>"},
    ),
    SourceSpec(
        "smartrecruiters", "SmartRecruiters", "ats", A.PUBLIC_API, 1,
        C.ALREADY_CANONICAL, "smartrecruiters", M.IMPLEMENTED,
        "Documented public API: api.smartrecruiters.com/v1/companies/{id}/postings.",
        {"external_id": "<company id>"},
    ),
    SourceSpec(
        "workday", "Workday", "ats", A.PUBLIC_API, 1, C.ALREADY_CANONICAL,
        "workday", M.LIVE,
        "Public careers-site JSON. Tenants verified 2026-07-22 for TD, BMO, CIBC, "
        "Manulife and Sun Life (~4,600 postings reachable).",
        {"tenant": "<tenant>", "wd": 3, "site": "<site id>"},
    ),
    SourceSpec(
        "successfactors", "SAP SuccessFactors", "ats", A.PUBLIC_PAGE, 1,
        C.ALREADY_CANONICAL, "jsonld", M.PROBE,
        "Per-tenant. Most public SuccessFactors career sites emit JSON-LD, so the "
        "generic JSON-LD connector should cover them once a tenant URL is known.",
    ),
    SourceSpec(
        "icims", "iCIMS", "ats", A.PUBLIC_PAGE, 1, C.ALREADY_CANONICAL,
        "jsonld", M.PROBE,
        "iCIMS portals are HTML; JSON-LD is present on many job detail pages. "
        "Needs a concrete portal URL to verify.",
    ),
    SourceSpec(
        "taleo_orc", "Oracle Recruiting / Taleo", "ats", A.PUBLIC_API, 1,
        C.ALREADY_CANONICAL, "oracle_orc", M.IMPLEMENTED,
        "Oracle Cloud Recruiting public REST resource "
        "(recruitingCEJobRequisitions). Needs a tenant host to verify.",
        {"host": "<tenant>.oraclecloud.com", "site": "CX_1"},
    ),
    SourceSpec(
        "jsonld_career_page", "Generic career page (JSON-LD)", "ats",
        A.PUBLIC_PAGE, 1, C.ALREADY_CANONICAL, "jsonld", M.IMPLEMENTED,
        "schema.org/JobPosting embedded in the employer's own page. One connector "
        "unlocks many employers at once; unit-tested against sample markup.",
        {"urls": ["<career page urls>"]},
    ),
    SourceSpec(
        "sitemap_career_page", "Generic career page (sitemap)", "ats",
        A.PUBLIC_PAGE, 1, C.ALREADY_CANONICAL, "sitemap", M.IMPLEMENTED,
        "sitemap.xml -> job URLs -> JSON-LD extraction per page.",
        {"sitemap_url": "<sitemap>", "job_pattern": "job|career"},
    ),
]

# ---------------------------------------------------------------------------
# 11-16  Government and public sector
# ---------------------------------------------------------------------------
GOVERNMENT: list[SourceSpec] = [
    SourceSpec(
        "job_bank", "Canada Job Bank", "government", A.PUBLIC_PAGE, 2,
        C.RESOLVE_TO_EMPLOYER, "jsonld", M.NEEDS_ENDPOINT,
        "PROBED 2026-07-22: reachable (HTTP 200, 283KB) but the search page "
        "carries no JSON-LD. Needs a real listing endpoint.",
    ),
    SourceSpec(
        "gc_jobs", "GC Jobs (federal public service)", "government",
        A.PUBLIC_PAGE, 2, C.ALREADY_CANONICAL, "jsonld", M.PROBE,
        "PROBED 2026-07-22: connection failed on the guessed URL; the correct "
        "entry point is still unknown.",
    ),
    SourceSpec(
        "ontario_public_service", "Ontario Public Service", "government",
        A.PUBLIC_PAGE, 2, C.ALREADY_CANONICAL, "jsonld", M.NEEDS_ENDPOINT,
        "PROBED 2026-07-22: gojobs.gov.on.ca reachable (486KB) but no JSON-LD.",
    ),
    SourceSpec(
        "city_of_toronto", "City of Toronto", "government", A.PUBLIC_PAGE, 2,
        C.ALREADY_CANONICAL, "oracle_orc", M.PROBE,
        "PROBED 2026-07-22: jobs.toronto.ca reachable but JS-rendered. Likely "
        "Oracle ORC underneath — needs the tenant host and site id.",
    ),
    SourceSpec(
        "ttc", "Toronto Transit Commission", "government", A.PUBLIC_PAGE, 2,
        C.ALREADY_CANONICAL, "jsonld", M.PROBE,
        "PROBED 2026-07-22: careers.ttc.ca does not resolve; host unknown.",
    ),
    SourceSpec(
        "metrolinx", "Metrolinx", "government", A.PUBLIC_PAGE, 2,
        C.ALREADY_CANONICAL, "jsonld", M.PROBE,
        "PROBED 2026-07-22: careers.metrolinx.com does not resolve.",
    ),
]

# ---------------------------------------------------------------------------
# 17-19  Sources tied to the user's own account => USER IMPORT ONLY.
# The system never logs in as the user and never scrapes an authenticated
# session (docs/SECURITY.md; account automation is a PRD non-goal).
# ---------------------------------------------------------------------------
USER_SOURCES: list[SourceSpec] = [
    SourceSpec(
        "uoft_clnx", "UofT CLNx / Co-op portal", "institution", A.USER_IMPORT, 2,
        C.RESOLVE_TO_EMPLOYER, "user_import", M.IMPLEMENTED,
        "PROBED 2026-07-22: HTTP 403 without a session, exactly as expected. "
        "Behind student login — the user exports or pastes postings and the "
        "system never authenticates as the student.",
    ),
    SourceSpec(
        "linkedin", "LinkedIn (user import)", "aggregator", A.USER_IMPORT, 3,
        C.RESOLVE_TO_EMPLOYER, "user_import", M.IMPLEMENTED,
        "Account automation is an explicit non-goal. Saved-jobs export or pasted "
        "URLs only; every posting must resolve to the employer's own ATS.",
    ),
    SourceSpec(
        "indeed_email", "Indeed job alert emails", "aggregator", A.USER_IMPORT, 3,
        C.RESOLVE_TO_EMPLOYER, "user_import", M.IMPLEMENTED,
        "Parsed from alert emails the user forwards or connects — never by "
        "scraping Indeed.",
    ),
]

# ---------------------------------------------------------------------------
# 20-25  Ecosystem / community boards — discovery only.
# ---------------------------------------------------------------------------
ECOSYSTEM: list[SourceSpec] = [
    SourceSpec(
        "techto", "TechTO", "ecosystem", A.PUBLIC_PAGE, 3, C.RESOLVE_TO_EMPLOYER,
        "jsonld", M.NEEDS_ENDPOINT,
        "PROBED 2026-07-22: jobs.techto.org reachable (544KB) but JS-rendered "
        "with no JSON-LD in the initial HTML.",
    ),
    SourceSpec(
        "communitech", "Communitech", "ecosystem", A.PUBLIC_PAGE, 3,
        C.RESOLVE_TO_EMPLOYER, "jsonld", M.PROBE,
        "PROBED 2026-07-22: jobs.communitech.ca does not resolve.",
    ),
    SourceSpec(
        "mars", "MaRS Discovery District", "ecosystem", A.PUBLIC_PAGE, 3,
        C.RESOLVE_TO_EMPLOYER, "jsonld", M.NEEDS_ENDPOINT,
        "PROBED 2026-07-22: reachable but no JSON-LD job postings found.",
    ),
    SourceSpec(
        "vector_talent", "Vector Institute Talent Hub", "ecosystem",
        A.PUBLIC_PAGE, 3, C.RESOLVE_TO_EMPLOYER, "jsonld", M.NEEDS_ENDPOINT,
        "PROBED 2026-07-22: reachable but no JSON-LD on the careers page.",
    ),
    SourceSpec(
        "dmz", "DMZ (TMU)", "ecosystem", A.PUBLIC_PAGE, 3, C.RESOLVE_TO_EMPLOYER,
        "jsonld", M.PROBE,
        "PROBED 2026-07-22: the guessed careers path returned 404.",
    ),
    SourceSpec(
        "wellfound", "Wellfound", "aggregator", A.USER_IMPORT, 3,
        C.RESOLVE_TO_EMPLOYER, "user_import", M.BLOCKED,
        "PROBED 2026-07-22: returns HTTP 403 to automated requests. The site "
        "declines automated access, so we do NOT scrape it. Reclassified to user "
        "import: paste postings found there and the system resolves them to the "
        "employer's official ATS.",
    ),
]

CATALOG: list[SourceSpec] = [*ATS, *GOVERNMENT, *USER_SOURCES, *ECOSYSTEM]
BY_KEY: dict[str, SourceSpec] = {s.key: s for s in CATALOG}


def requires_canonical_resolution(key: str) -> bool:
    spec = BY_KEY.get(key)
    return bool(spec and spec.canonical_policy is C.RESOLVE_TO_EMPLOYER)


def summary() -> dict:
    counts: dict[str, int] = {}
    for s in CATALOG:
        counts[s.maturity.value] = counts.get(s.maturity.value, 0) + 1
    return {"total": len(CATALOG), "by_maturity": counts}
