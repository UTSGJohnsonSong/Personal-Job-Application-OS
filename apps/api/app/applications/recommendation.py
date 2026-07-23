"""Recommended Application Set — how many roles to apply to at one company.

Two failure modes to avoid, in both directions:

* Spraying near-identical requisitions at one employer. It wastes the user's
  time, is hard to track, and reads as unfocused to the recruiting team.
* A blunt "one application per company" rule. Large employers run genuinely
  separate teams, locations, terms and hiring processes, and those deserve
  separate applications.

So the limit is a default, and redundancy is judged from the roles themselves.
The algorithm is a transparent greedy pass — no opaque optimiser — and every
inclusion and exclusion records its reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.company.portfolio import CompanyEntry, RoleEntry, RoleFamily
from app.ingestion.normalize import title_core

# Default recommended applications per company, per hiring cycle.
DEFAULT_LIMIT = 3
TIER_LIMITS = {"S": 4, "A": 3, "B": 3, "C": 2, "D": 2}

# Similarity thresholds.
TITLE_OVERLAP_SIMILAR = 0.7
REDUNDANCY_HIGH = 0.75

_SENIORITY = re.compile(r"\b(intern|internship|co-?op|student|new grad|junior|senior)\b",
                        re.I)


def _title_tokens(title: str) -> set[str]:
    core = title_core(title)
    tokens = {t for t in core.split() if len(t) > 2}
    # Drop term/seniority words: they do not distinguish two roles at the same
    # employer, since almost every student posting carries them.
    return {t for t in tokens if not _SENIORITY.fullmatch(t)}


def title_similarity(a: str, b: str) -> float:
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def location_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.5          # unknown: neither same nor clearly different
    return 1.0 if a.strip().lower() == b.strip().lower() else 0.0


def redundancy_risk(a: RoleEntry, b: RoleEntry) -> float:
    """0..1 estimate that applying to both adds little over applying to one."""
    if a.family is not b.family:
        # Different role families are genuinely different applications.
        base = 0.15
    else:
        base = 0.55

    title = title_similarity(a.title, b.title)
    same_dept = (a.department and b.department
                 and a.department.strip().lower() == b.department.strip().lower())
    loc = location_similarity(a.location, b.location)

    risk = base + 0.35 * title + (0.10 if same_dept else 0.0) + 0.10 * loc
    # Same band and family and near-identical title => clearly redundant.
    if a.family is b.family and a.role_band == b.role_band and title >= TITLE_OVERLAP_SIMILAR:
        risk = max(risk, 0.85)
    return round(min(1.0, risk), 3)


@dataclass
class SimilarityGroup:
    group_id: str
    members: list[RoleEntry] = field(default_factory=list)

    @property
    def best(self) -> RoleEntry:
        return max(self.members, key=lambda r: r.application_priority)


def cluster_similar_roles(roles: list[RoleEntry]) -> list[SimilarityGroup]:
    """Greedy single-link clustering on redundancy risk."""
    groups: list[SimilarityGroup] = []
    for role in sorted(roles, key=lambda r: -r.application_priority):
        placed = False
        for group in groups:
            if any(redundancy_risk(role, m) >= REDUNDANCY_HIGH for m in group.members):
                group.members.append(role)
                role.similarity_group_id = group.group_id
                placed = True
                break
        if not placed:
            gid = f"grp-{len(groups) + 1}"
            role.similarity_group_id = gid
            groups.append(SimilarityGroup(group_id=gid, members=[role]))
    return groups


@dataclass
class Recommendation:
    role: RoleEntry
    reason: str
    rank: int


@dataclass
class ExcludedRole:
    role: RoleEntry
    reason: str
    superseded_by: str | None = None


@dataclass
class ApplicationSet:
    company: CompanyEntry
    limit: int
    recommended: list[Recommendation] = field(default_factory=list)
    excluded: list[ExcludedRole] = field(default_factory=list)
    already_applied: int = 0
    over_limit: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return (f"{self.company.name}: recommend {len(self.recommended)} of "
                f"{len(self.company.relevant_roles)} relevant roles "
                f"(limit {self.limit})")


def build_application_set(
    company: CompanyEntry,
    *,
    limit: int | None = None,
    include_review: bool = False,
) -> ApplicationSet:
    """Pick the small set of roles genuinely worth applying to at one company.

    Greedy and explainable:
      1. keep eligible roles (REVIEW only when the user opted in)
      2. order by Application Priority
      3. cluster near-duplicate requisitions, keep the best of each cluster
      4. prefer covering distinct role families
      5. respect the per-company limit, stating the reason when it binds
      6. damp anything already covered by a submitted application
    """
    tier_limit = TIER_LIMITS.get(company.bucket, DEFAULT_LIMIT)
    cap = limit if limit is not None else tier_limit
    result = ApplicationSet(company=company, limit=cap)

    eligible = [r for r in company.relevant_roles
                if r.eligibility == "PASS"
                or (include_review and r.eligibility == "REVIEW")]
    for r in company.relevant_roles:
        if r not in eligible:
            result.excluded.append(ExcludedRole(
                r, f"eligibility {r.eligibility} — needs manual review before applying"))

    applied = company.applied_roles
    result.already_applied = len(applied)

    groups = cluster_similar_roles(eligible)

    # Best of each cluster; the rest are recorded as redundant.
    candidates: list[RoleEntry] = []
    for group in groups:
        best = group.best
        candidates.append(best)
        for member in group.members:
            if member is best:
                continue
            result.excluded.append(ExcludedRole(
                member,
                "highly similar to a higher-priority role at this company",
                superseded_by=best.title,
            ))

    # Already-submitted work suppresses near-duplicates of itself.
    filtered: list[RoleEntry] = []
    for role in candidates:
        clash = next((a for a in applied if redundancy_risk(role, a) >= REDUNDANCY_HIGH),
                     None)
        if clash:
            result.excluded.append(ExcludedRole(
                role, "you already applied to a near-identical role",
                superseded_by=clash.title))
            continue
        filtered.append(role)

    filtered.sort(key=lambda r: -r.application_priority)

    # Greedy selection favouring family diversity once the top pick is in.
    chosen: list[RoleEntry] = []
    families: set[RoleFamily] = set()
    for role in filtered:
        if len(chosen) >= cap:
            result.excluded.append(ExcludedRole(
                role, f"beyond the recommended limit of {cap} for this company"))
            result.over_limit = True
            continue
        # After the first pick, prefer a new family when scores are close.
        if chosen and role.family in families:
            better_elsewhere = next(
                (r for r in filtered
                 if r not in chosen and r.family not in families
                 and r.application_priority >= role.application_priority - 8),
                None,
            )
            if better_elsewhere:
                continue
        chosen.append(role)
        families.add(role.family)

    for i, role in enumerate(chosen, start=1):
        bits = [f"priority {role.application_priority:.0f}",
                f"{role.role_band}/{role.family.value}"]
        if not role.is_official:
            bits.append("no official link yet — resolve before applying")
        result.recommended.append(
            Recommendation(role=role, rank=i, reason=" · ".join(bits)))

    if result.over_limit:
        result.notes.append(
            f"More qualifying roles exist than the recommended {cap}. Applying to "
            "many near-identical requisitions at one employer rarely helps; "
            "override deliberately if these are genuinely different teams."
        )
    if len(groups) < len(eligible):
        result.notes.append(
            f"{len(eligible) - len(groups)} role(s) were near-duplicates of a "
            "higher-priority posting and were folded into it."
        )
    if not chosen and eligible:
        result.notes.append(
            "Nothing recommended: every eligible role duplicates something you "
            "already applied to."
        )
    return result


def build_all_sets(
    companies: list[CompanyEntry], *, include_review: bool = False
) -> list[ApplicationSet]:
    sets = [build_application_set(c, include_review=include_review)
            for c in companies]
    sets.sort(key=lambda s: -(s.recommended[0].role.application_priority
                              if s.recommended else 0))
    return sets
