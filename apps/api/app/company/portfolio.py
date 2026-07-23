"""Company-centric organisation of the job inbox.

Product rule (docs/COMPANY_INBOX.md):

    Company Tier organises COMPANIES.
    Application Priority orders ROLES.

Tier is therefore a grouping axis, never a hard ceiling: an A-tier role at
priority 94 outranks an S-tier role at 84 in the global queue. Scoring formulas
are untouched here — this module only organises what they already produced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    company_platform_value: float = 0.0
    role_strategic_value: float = 0.0
    current_fit: float = 0.0
    team_quality: float = 0.0
    career_optionality: float = 0.0
    evidence_coverage: float = 0.0
    recommendation: str = ""
    similarity_group_id: str | None = None

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
    pairs.sort(key=lambda pair: -pair[1].application_priority)
    return pairs[:limit] if limit else pairs


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
