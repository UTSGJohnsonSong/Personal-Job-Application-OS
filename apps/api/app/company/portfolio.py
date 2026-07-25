"""Company-centric organisation of the job inbox.

Product rule (docs/COMPANY_INBOX.md):

    Company Tier organises COMPANIES.
    Application Priority orders ROLES.

Tier is therefore a grouping axis, never a hard ceiling: an A-tier role at
priority 94 outranks an S-tier role at 84 in the global queue. Scoring formulas
are untouched here — this module only organises what they already produced.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

# Companies whose evidence is too thin for a formal rating are never shown in a
# real tier; they get their own bucket so they are neither trusted nor buried.
PROVISIONAL_BUCKET = "Provisional / Needs Research"

TIER_ORDER = ["S", "A", "B", "C", "D", PROVISIONAL_BUCKET]

# How many roles a company card shows by default, per tier. Display only —
# nothing is discarded from storage.
DEFAULT_VISIBLE_ROLES = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 2,
                         PROVISIONAL_BUCKET: 2}


class RoleFamily(StrEnum):
    """Coarse families used for diversity and redundancy reasoning."""

    SOFTWARE = "software"
    BACKEND = "backend"
    DATA_ENGINEERING = "data_engineering"
    MACHINE_LEARNING = "machine_learning"
    PLATFORM_INFRA = "platform_infra"
    ANALYTICS = "analytics"
    PRODUCT = "product"
    PROGRAM = "program"
    OTHER = "other"


ROLE_TYPE_TO_FAMILY: dict[str, RoleFamily] = {
    "software_engineering": RoleFamily.SOFTWARE,
    "backend_engineering": RoleFamily.BACKEND,
    "data_engineering": RoleFamily.DATA_ENGINEERING,
    "machine_learning_engineering": RoleFamily.MACHINE_LEARNING,
    "applied_ai": RoleFamily.MACHINE_LEARNING,
    "ml_infrastructure": RoleFamily.PLATFORM_INFRA,
    "platform_engineering": RoleFamily.PLATFORM_INFRA,
    "cloud_engineering": RoleFamily.PLATFORM_INFRA,
    "analytics_engineering": RoleFamily.ANALYTICS,
    "data_analyst": RoleFamily.ANALYTICS,
    "bi_analyst": RoleFamily.ANALYTICS,
    "data_platform_analyst": RoleFamily.ANALYTICS,
    "technical_product": RoleFamily.PRODUCT,
    "ai_product": RoleFamily.PRODUCT,
    "product_engineering": RoleFamily.PRODUCT,
    "general_product_analyst": RoleFamily.PRODUCT,
    "high_technical_product_analyst": RoleFamily.PRODUCT,
    "technical_program_management": RoleFamily.PROGRAM,
    "technical_project_management": RoleFamily.PROGRAM,
}


def role_family(role_type: str | None) -> RoleFamily:
    return ROLE_TYPE_TO_FAMILY.get((role_type or "").lower(), RoleFamily.OTHER)


@dataclass
class RoleEntry:
    """One scored role, as produced by the existing ranking pipeline."""

    job_id: str
    title: str
    role_type: str
    role_band: str                     # R1..R4
    application_priority: float
    eligibility: str                   # PASS / REVIEW / FAIL
    location: str = ""
    department: str | None = None
    canonical_url: str | None = None
    discovery_url: str | None = None
    is_student_role: bool = False
    already_applied: bool = False
    # Other places the same opportunity is advertised. Populated when the
    # global queue collapses one role that was posted once per location.
    other_locations: list[str] = field(default_factory=list)
    company_platform_value: float = 0.0
    role_strategic_value: float = 0.0
    current_fit: float = 0.0
    team_quality: float = 0.0
    career_optionality: float = 0.0
    evidence_coverage: float = 0.0
    recommendation: str = ""
    similarity_group_id: str | None = None
    application_deadline: datetime | None = None

    @property
    def family(self) -> RoleFamily:
        return role_family(self.role_type)

    @property
    def is_official(self) -> bool:
        """Only a canonical (employer-owned) link counts as official."""
        return bool(self.canonical_url)


@dataclass
class CompanyEntry:
    company_id: str
    name: str
    tier: str                          # S/A/B/C/D
    tier_display: str                  # e.g. "A" or "A?"
    provisional: bool
    platform_value: float
    evidence_coverage: float
    roles: list[RoleEntry] = field(default_factory=list)
    last_checked: str | None = None
    official_source_coverage: float = 0.0

    @property
    def bucket(self) -> str:
        """Provisional companies never appear inside a formal tier."""
        return PROVISIONAL_BUCKET if self.provisional else self.tier

    @property
    def relevant_roles(self) -> list[RoleEntry]:
        """Roles worth showing: eligible, not already applied to."""
        return [r for r in self.roles
                if r.eligibility != "FAIL" and not r.already_applied]

    @property
    def student_roles(self) -> list[RoleEntry]:
        return [r for r in self.relevant_roles if r.is_student_role]

    @property
    def applied_roles(self) -> list[RoleEntry]:
        return [r for r in self.roles if r.already_applied]

    def ranked_roles(self) -> list[RoleEntry]:
        """In-company ordering is by Application Priority, highest first."""
        return sorted(self.relevant_roles,
                      key=lambda r: -r.application_priority)

    def top_roles(self, limit: int | None = None) -> list[RoleEntry]:
        n = limit if limit is not None else DEFAULT_VISIBLE_ROLES.get(self.bucket, 3)
        return self.ranked_roles()[:n]

    @property
    def best_priority(self) -> float:
        ranked = self.ranked_roles()
        return ranked[0].application_priority if ranked else 0.0

    @property
    def high_potential_unrated(self) -> bool:
        """Unknown company that nonetheless looks excellent on role evidence.

        Such a company must surface for research rather than be buried just
        because we have not rated it yet.
        """
        if not self.provisional:
            return False
        ranked = self.ranked_roles()
        if not ranked:
            return False
        best = ranked[0]
        return best.role_strategic_value >= 70 and best.current_fit >= 70


@dataclass
class TierGroup:
    tier: str
    companies: list[CompanyEntry]

    @property
    def company_count(self) -> int:
        return len(self.companies)

    @property
    def role_count(self) -> int:
        return sum(len(c.relevant_roles) for c in self.companies)


def group_by_tier(companies: list[CompanyEntry]) -> list[TierGroup]:
    """View 1: organise companies into tiers, best company first within a tier."""
    buckets: dict[str, list[CompanyEntry]] = {t: [] for t in TIER_ORDER}
    for c in companies:
        buckets.setdefault(c.bucket, []).append(c)

    groups: list[TierGroup] = []
    for tier in TIER_ORDER:
        members = buckets.get(tier) or []
        if not members:
            continue
        # Inside a tier, lead with the company holding the strongest role.
        members.sort(key=lambda c: (-c.best_priority, -c.platform_value, c.name))
        groups.append(TierGroup(tier=tier, companies=members))
    return groups


def global_priority_queue(
    companies: list[CompanyEntry], *, limit: int | None = None
) -> list[tuple[CompanyEntry, RoleEntry]]:
    """View 2: one flat queue ordered purely by Application Priority.

    Tier is displayed but must NOT group or cap this list — that is the whole
    point of "company-centric management, opportunity-centric ranking".
    """
    pairs = [(c, r) for c in companies for r in c.relevant_roles]
    # Eligibility breaks ties before collapsing. The same role posted in
    # Toronto and in Washington scores identically, and keeping whichever came
    # first would surface the one he cannot apply to.
    pairs.sort(key=lambda pair: (-pair[1].application_priority,
                                 _ELIGIBILITY_RANK.get(pair[1].eligibility, 3)))
    pairs = _collapse_same_role(pairs)
    return pairs[:limit] if limit else pairs


_ELIGIBILITY_RANK = {"PASS": 0, "REVIEW": 1, "FAIL": 2}


def _role_key(company: CompanyEntry, role: RoleEntry) -> tuple[str, str]:
    """Identity of an opportunity, independent of where it is advertised."""
    title = (role.title or "").lower()
    # Employers commonly append the location to an otherwise identical title.
    title = re.sub(r"\s*[\(\[][^)\]]*(remote|hybrid|onsite)[^)\]]*[\)\]]", " ", title)
    title = re.sub(r"\s*[-—–]\s*(100% )?remote.*$", " ", title)
    title = re.sub(r"[^a-z0-9]+", " ", title).strip()
    return (company.company_id, title)


def _collapse_same_role(
    pairs: list[tuple[CompanyEntry, RoleEntry]],
) -> list[tuple[CompanyEntry, RoleEntry]]:
    """One row per opportunity, not one row per posting.

    Employers routinely publish the same role once per location: Hopper had a
    single backend opening listed ten times across Vancouver, the Netherlands,
    Ireland, the UK, the US, New York, Argentina, Uruguay, Brazil and Spain.
    Each is a distinct requisition with its own id, so nothing upstream is
    wrong — but showing ten rows for one opportunity buries everything else.

    Input is already sorted by priority, so the first occurrence is the best
    one and the rest are recorded as alternate locations rather than dropped.
    """
    best: dict[tuple[str, str], tuple[CompanyEntry, RoleEntry]] = {}
    out: list[tuple[CompanyEntry, RoleEntry]] = []
    for company, role in pairs:
        key = _role_key(company, role)
        kept = best.get(key)
        if kept is None:
            best[key] = (company, role)
            out.append((company, role))
            continue
        if role.location and role.location not in kept[1].other_locations:
            kept[1].other_locations.append(role.location)
    return out


def companies_requiring_action(
    companies: list[CompanyEntry], *, min_priority: float = 70.0
) -> list[tuple[CompanyEntry, list[str]]]:
    """Companies with something actionable, with the reasons spelled out."""
    out: list[tuple[CompanyEntry, list[str]]] = []
    for c in companies:
        reasons: list[str] = []
        strong = [r for r in c.relevant_roles
                  if r.application_priority >= min_priority]
        if strong:
            reasons.append(f"{len(strong)} role(s) at priority ≥ {min_priority:.0f}")
        review = [r for r in c.relevant_roles if r.eligibility == "REVIEW"]
        if review:
            reasons.append(f"{len(review)} need manual review")
        if c.high_potential_unrated:
            reasons.append("high-potential but unrated — needs company research")
        third_party_only = [r for r in c.relevant_roles if not r.is_official]
        if third_party_only:
            reasons.append(
                f"{len(third_party_only)} role(s) lack an official link"
            )
        if reasons:
            out.append((c, reasons))
    out.sort(key=lambda pair: -pair[0].best_priority)
    return out


# ============================================================================
# Recommended / Backup role selection (2026-07-24).
#
# Deliberately a UNIFORM score threshold across every company, not a
# per-tier one. Application Priority already spends 38% of its weight on
# Company Platform Value — a per-tier threshold (e.g. "S needs 72, C only
# needs 48") would apply that same tier signal a second time and produce
# exactly the contradiction this design avoids: a 71-point S-tier role
# reading "Backup" while a 63-point A-tier role reads "Recommended", even
# though 71 > 63 on the one number that's supposed to settle it. Company
# tier controls a DIFFERENT thing here — how many roles a company must
# clear before the shortfall backfill kicks in — never the bar itself.
#
# Versioned and NOT auto-recalibrated against the live score distribution:
# thresholds are a deliberate policy decision, reviewed by hand against
# real postings, not a moving target that silently relabels every job the
# next time the job pool or formula shifts.
# ============================================================================
THRESHOLD_POLICY_VERSION = "v1-2026-07-24"
STRONG_RECOMMENDED_THRESHOLD = 72.0
RECOMMENDED_THRESHOLD = 64.0
BACKUP_FLOOR = 50.0

# How many roles a company must clear (Recommended + Backup combined) before
# the shortfall message applies instead of forcing a fill.
MIN_DISPLAY_COUNT: dict[str, int] = {
    "S": 3, "A": 3, "B": 2, "C": 1, "D": 1, PROVISIONAL_BUCKET: 1,
}

_YEAR = re.compile(r"\b20\d{2}\b")
_TRAILING_LOC = re.compile(r"\s*[-(].*$")


def _dedup_key(title: str) -> str:
    """Same company, same role stripped of year/location suffixes.

    A rough approximation ("Data Analyst - Toronto" and "Data Analyst
    (Vancouver)" collapse to the same key) — it can over-merge a role that
    happens to share a prefix before its first hyphen/paren but is actually
    a different team. Accepted tradeoff for catching the far more common
    case of the same req cross-posted per city or reposted per intake.
    """
    t = _YEAR.sub("", title or "")
    t = _TRAILING_LOC.sub("", t)
    return re.sub(r"[^a-z0-9]+", "", t.lower())


@dataclass
class RoleSelection:
    """What to actually show for one company: two labelled buckets.

    `recommended` meets the uniform bar on its own merits. `backup` exists
    only to keep a company from looking empty when it hasn't cleared that
    bar — never a claim that these are equally good, and never a rewrite of
    their own score. `strong_job_ids` marks which recommended roles also
    clear the higher bar, for a "Strong Recommended" badge without a third
    bucket.
    """

    recommended: list[RoleEntry]
    backup: list[RoleEntry]
    strong_job_ids: set[str]
    shortfall_message: str | None
    policy_version: str = THRESHOLD_POLICY_VERSION


def select_company_roles(entry: CompanyEntry, *, now: datetime | None = None) -> RoleSelection:
    """Partition one company's roles into Recommended / Backup for display.

    Recommended Application Set (app/applications/recommendation.py) is a
    separate, narrower decision about what to actually apply to — this
    function only controls what's worth SHOWING, and min_display_count is a
    display floor, not a claim that the user should apply to all of them.
    """
    now = now or datetime.now(UTC)
    eligible = [
        r for r in entry.relevant_roles
        if r.role_band != "R4"
        and (r.application_deadline is None or r.application_deadline > now)
    ]
    eligible.sort(key=lambda r: -r.application_priority)

    recommended = [r for r in eligible if r.application_priority >= RECOMMENDED_THRESHOLD]
    strong_ids = {r.job_id for r in recommended
                 if r.application_priority >= STRONG_RECOMMENDED_THRESHOLD}

    min_count = MIN_DISPLAY_COUNT.get(entry.bucket, 2)
    backup: list[RoleEntry] = []
    if len(recommended) < min_count:
        recommended_ids = {r.job_id for r in recommended}
        seen_keys = {_dedup_key(r.title) for r in recommended}
        for r in eligible:
            if len(recommended) + len(backup) >= min_count:
                break
            if r.job_id in recommended_ids:
                continue
            if r.application_priority < BACKUP_FLOOR:
                continue
            key = _dedup_key(r.title)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            backup.append(r)

    total = len(recommended) + len(backup)
    shortfall = (
        None if total >= min_count
        else f"Only {total} eligible role{'s' if total != 1 else ''} found."
    )

    return RoleSelection(
        recommended=recommended, backup=backup, strong_job_ids=strong_ids,
        shortfall_message=shortfall,
    )
