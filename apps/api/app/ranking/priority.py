"""Application Priority — six independent scores, never one "match %".

2026-07-24 redesign. The previous version put company standing into the
score twice — 50% directly as company_platform_value, then again inside
career_optionality's `0.6 * company_score + 0.4 * transferability` (which
was also silently never added to the total, a separate bug). It also put
"real delivery / ownership" evidence into both role_strategic_value and
team_project_quality, and injected a Tier x Role bonus AND a hard floor on
top of the six weights — none of which the six-weight system was supposed
to need once each dimension answers one question with no overlap:

  company_platform_value   — is this employer worth having on a resume?
  role_strategic_value     — is THIS posting's direction/depth on-target?
  team_project_quality     — what would he actually be doing day to day?
  current_candidate_fit    — does he already have the skills this JD wants?
  career_optionality       — what does finishing this open up next?
  opportunity_viability     — is this a real, live, currently-applicable posting?

Eligibility is a gate (app/ranking/gate.py), never a score contribution.
Action urgency and application effort are computed but NEVER weighted into
application_priority — a deadline in 2 days doesn't make a job better, an
easy application doesn't either; both only affect which order to work
through an already-ranked list. No tier bonus, no priority floor: company
standing is captured once, at its own weight, full stop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.company.intelligence import CompanyIntelligence
from app.ranking.gate import Gate, GateResult
from app.ranking.modes import RankingProfile
from app.roles.taxonomy import RoleBand, RoleClassification
from app.skills.ontology import FitBreakdown


@dataclass
class ScoreWithCoverage:
    """A score that always travels with its coverage — never bare precision."""

    known_evidence: float | None   # 0..100, None = unknown
    coverage: float                # 0..1
    conservative: float            # 0..100
    is_prior: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def display(self) -> str:
        if self.known_evidence is None:
            return "Insufficient Data"
        return f"{self.conservative:.0f}"


@dataclass
class RoleStrategicValue:
    """Answers ONE question: is this posting's direction/depth on-target?

    Deliberately excludes career transferability (that's career_optionality's
    job) and delivery/ownership evidence (that's team_project_quality's job)
    — both used to live here too, double-counting the same JD text twice.
    """

    score: float
    coverage: float
    role_family_alignment: float
    technical_depth: float
    growth_scope: float
    title_readability: float
    evidence: list[str] = field(default_factory=list)


@dataclass
class PriorityResult:
    # --- gate ---
    eligibility: GateResult
    # --- six independent, weighted scores (0..100) ---
    company_platform_value: ScoreWithCoverage
    role_strategic_value: ScoreWithCoverage
    team_project_quality: ScoreWithCoverage
    current_candidate_fit: ScoreWithCoverage
    career_optionality: ScoreWithCoverage
    opportunity_viability: ScoreWithCoverage
    contributions: dict[str, float]              # per-dimension points in the total
    application_priority: float                  # 0..100, NOT a match %
    # --- informational only: NEVER fed into application_priority ---
    action_urgency: str                           # urgent | soon | normal | low | unknown
    application_effort_minutes: int
    # --- context ---
    role_band: str
    role_type: str
    company_tier: str
    company_tier_display: str
    evidence_coverage: float
    freshness: float
    recommendation: str                          # Serious Apply / ... / Skip
    interaction_rule: str
    transferability: float
    why: list[str] = field(default_factory=list)
    why_not: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    formula_version: str = "v3"

    def as_dict(self) -> dict:
        return {
            "eligibility": self.eligibility.gate.value,
            "eligibility_verdict": self.eligibility.verdict,
            "company_tier": self.company_tier,
            "company_tier_display": self.company_tier_display,
            "company_platform_value": self.company_platform_value.conservative,
            "role_category": self.role_band,
            "role_type": self.role_type,
            "role_strategic_value": self.role_strategic_value.conservative,
            "current_candidate_fit": self.current_candidate_fit.conservative,
            "current_fit_known_evidence": self.current_candidate_fit.known_evidence,
            "current_fit_coverage": self.current_candidate_fit.coverage,
            "team_project_quality": self.team_project_quality.conservative,
            "career_optionality": self.career_optionality.conservative,
            "opportunity_viability": self.opportunity_viability.conservative,
            "evidence_coverage": self.evidence_coverage,
            "contributions": self.contributions,
            "application_priority": self.application_priority,
            "action_urgency": self.action_urgency,
            "application_effort_minutes": self.application_effort_minutes,
            "recommendation": self.recommendation,
            "interaction_rule": self.interaction_rule,
            "why": self.why,
            "why_not": self.why_not,
            "unknowns": self.unknowns,
            "formula_version": self.formula_version,
        }


# --------------------------------------------------------------------------
# Role Strategic Value — direction/depth of THIS posting, nothing else.
# --------------------------------------------------------------------------
_RSV_WEIGHTS = {
    "role_family_alignment": 0.45,
    "technical_depth": 0.30,
    "growth_scope": 0.20,
    "title_readability": 0.05,
}

_DIRECTION_ALIGNMENT = {
    "software_engineering": 0.85, "backend_engineering": 1.0,
    "data_engineering": 1.0, "machine_learning_engineering": 1.0,
    "applied_ai": 1.0, "ml_infrastructure": 0.95, "platform_engineering": 0.85,
    "cloud_engineering": 0.8, "analytics_engineering": 0.8,
    "technical_product": 0.75, "ai_product": 0.85, "product_engineering": 0.75,
    "technical_program_management": 0.6, "data_platform_analyst": 0.7,
    "high_technical_product_analyst": 0.7, "data_analyst": 0.55,
    "bi_analyst": 0.5, "business_systems_analyst": 0.4,
    "technology_analyst": 0.45, "solutions_engineer": 0.35,
    "technical_project_management": 0.35, "general_product_analyst": 0.35,
    "sales": 0.05, "customer_support": 0.05, "hr": 0.0,
    "general_marketing": 0.05, "nontechnical_operations": 0.1,
    "administrative": 0.0, "nontechnical_business_development": 0.05,
    "nontechnical_finance_ops": 0.05, "unknown": 0.3,
}

# Structural scope by role band — deliberately NOT a JD-text signal. This is
# "does this TYPE of role typically carry broad individual scope", which is
# a property of the role category itself; whether THIS specific posting
# actually delivers on that is team_project_quality's question, evaluated
# from the JD text separately so the two never read the same words twice.
_SCOPE_BY_BAND = {
    RoleBand.R1: 0.8, RoleBand.R2: 0.65, RoleBand.R3: 0.45, RoleBand.R4: 0.15,
}


def compute_role_strategic_value(
    role: RoleClassification, description: str | None
) -> RoleStrategicValue:
    body = (description or "").lower()

    alignment = _DIRECTION_ALIGNMENT.get(role.role_type, 0.3)
    depth = role.technical_density
    scope = _SCOPE_BY_BAND[role.band]
    readability = 0.9 if role.band in (RoleBand.R1, RoleBand.R2) else (
        0.6 if role.band is RoleBand.R3 else 0.3
    )

    parts = {
        "role_family_alignment": alignment,
        "technical_depth": depth,
        "growth_scope": scope,
        "title_readability": readability,
    }
    score = sum(_RSV_WEIGHTS[k] * v for k, v in parts.items())
    coverage = 0.55 if not body else min(1.0, 0.7 + 0.3 * role.confidence)

    return RoleStrategicValue(
        score=round(score * 100, 2),
        coverage=round(coverage, 4),
        role_family_alignment=round(alignment, 3),
        technical_depth=round(depth, 3),
        growth_scope=round(scope, 3),
        title_readability=readability,
        evidence=role.evidence,
    )


# --------------------------------------------------------------------------
# Team / Project Quality — what he'd actually be doing, from the JD text.
# --------------------------------------------------------------------------
_CORE_SIGNALS = [
    "own", "design", "build", "architect", "ship", "core product",
    "core data", "greenfield", "end-to-end", "end to end",
]
_OWNERSHIP_SIGNALS = [
    "production", "deploy", "launch", "real users", "on-call", "oncall",
    "scale", "own the", "responsible for",
]
_SPECIFICITY_SIGNALS = [
    "api", "pipeline", "dashboard", "database", "service", "endpoint",
    "feature", "model", "schema", "algorithm",
]
_COLLAB_SIGNALS = [
    "team", "mentor", "collaborate", "code review", "pair programming",
    "cross-functional",
]
# Support/reporting-only phrasing — the opposite of "core, owned work".
_NEGATIVE_SIGNALS = [
    "data entry", "administrative support", "reporting only",
    "assist the team", "assist with", "under close supervision",
    "generate reports", "shadow the", "observe the",
]


def compute_team_quality(description: str | None) -> ScoreWithCoverage:
    """Is the actual work real, owned and tellable in an interview?

    Deliberately separate from role_strategic_value: that dimension asks
    whether the ROLE TYPE is on-target; this one reads the same JD text for
    a different question — is the day-to-day itself substantial, or is this
    a "core" title with support/reporting-shaped actual work.
    """
    body = (description or "").lower()
    if not body:
        return ScoreWithCoverage(None, 0.0, 50.0, is_prior=True,
                                 notes=["no job description available"])

    core_hits = sum(1 for s in _CORE_SIGNALS if s in body)
    own_hits = sum(1 for s in _OWNERSHIP_SIGNALS if s in body)
    spec_hits = sum(1 for s in _SPECIFICITY_SIGNALS if s in body)
    collab_hits = sum(1 for s in _COLLAB_SIGNALS if s in body)
    neg_hits = sum(1 for s in _NEGATIVE_SIGNALS if s in body)

    core_score = min(1.0, core_hits / 4.0)
    ownership_score = min(1.0, own_hits / 4.0)
    specificity_score = min(1.0, spec_hits / 4.0)
    collab_score = min(1.0, collab_hits / 3.0)
    negative_penalty = min(1.0, neg_hits / 3.0)

    raw = (
        0.30 * core_score + 0.30 * ownership_score
        + 0.20 * specificity_score + 0.10 * collab_score
    )
    raw = max(0.0, raw - 0.10 * negative_penalty)

    coverage = min(1.0, 0.4 + 0.06 * len(body) / 100)
    conservative = raw * coverage + 0.5 * (1 - coverage)
    notes = ["support/reporting-shaped language detected"] if neg_hits else []
    return ScoreWithCoverage(round(raw * 100, 2), round(coverage, 4),
                             round(conservative * 100, 2), notes=notes)


# --------------------------------------------------------------------------
# Career Optionality — what finishing this opens up next.
# --------------------------------------------------------------------------
_BREADTH_BY_BAND = {
    RoleBand.R1: 0.9, RoleBand.R2: 0.75, RoleBand.R3: 0.55, RoleBand.R4: 0.15,
}
_STORY_SIGNALS = [
    "launch", "results", "impact", "metrics", "deliver", "release",
    "portfolio", "presented", "demo",
]
# Capped deliberately small: this used to be 60% of the dimension (company
# score again), which meant company standing got counted twice —
# company_platform_value's own 38% weight, plus 60% of optionality's 10% =
# another 6 points hidden inside a dimension that was supposed to be about
# the CANDIDATE's future options. Now it's 10% of a 10%-weight dimension =
# at most 1 point of the final score, just enough to reflect that a bigger
# platform genuinely does offer more internal mobility.
_MOBILITY_BY_TIER = {"S": 1.0, "A": 0.8, "B": 0.6, "C": 0.4, "D": 0.2}


def compute_career_optionality(
    role: RoleClassification, company: CompanyIntelligence, description: str | None
) -> ScoreWithCoverage:
    body = (description or "").lower()

    transferability = role.transferability
    breadth = _BREADTH_BY_BAND[role.band]
    story_hits = sum(1 for s in _STORY_SIGNALS if s in body) if body else 0
    story_potential = min(1.0, story_hits / 3.0) if body else 0.3
    mobility = _MOBILITY_BY_TIER.get(company.system_tier, 0.5)

    raw = (
        0.40 * transferability + 0.30 * breadth
        + 0.20 * story_potential + 0.10 * mobility
    )
    coverage = 0.6 if not body else min(1.0, 0.7 + 0.3 * role.confidence)
    conservative = raw * coverage + 0.5 * (1 - coverage)
    return ScoreWithCoverage(round(raw * 100, 2), round(coverage, 4),
                             round(conservative * 100, 2))


# --------------------------------------------------------------------------
# Opportunity Viability — is this a real, live, currently-applicable
# posting? Explicitly NOT "how many days until the deadline" — that's
# action_urgency's job. A posting with no deadline listed isn't worse than
# one closing in 3 days; it just needs different handling.
# --------------------------------------------------------------------------
_TERM_WINDOW = re.compile(
    r"\b(fall|winter|summer|spring)\s*20\d{2}\b|\bcohort\b|\bintake\b", re.I)


def compute_opportunity_viability(
    freshness: float,
    source_status: str,
    application_deadline: datetime | None,
    description: str | None,
) -> ScoreWithCoverage:
    source_open = 1.0 if source_status == "open" else 0.3
    deadline_known = 1.0 if application_deadline is not None else 0.4
    term_clarity = 1.0 if (description and _TERM_WINDOW.search(description)) else 0.5

    raw = (
        0.35 * source_open + 0.30 * freshness
        + 0.20 * deadline_known + 0.15 * term_clarity
    )
    # High coverage always — these are all directly observed facts about the
    # posting itself, never guessed.
    coverage = 1.0
    return ScoreWithCoverage(round(raw * 100, 2), coverage, round(raw * 100, 2))


def compute_action_urgency(application_deadline: datetime | None) -> str:
    """When to act — informational only, never fed into application_priority."""
    if application_deadline is None:
        return "unknown"
    days = (application_deadline - datetime.now(UTC)).days
    if days <= 3:
        return "urgent"
    if days <= 7:
        return "soon"
    if days <= 21:
        return "normal"
    return "low"


# --------------------------------------------------------------------------
# Tier x Role interaction rules — a RECOMMENDATION LABEL only. Does not add
# or subtract points; company standing is captured once, in
# company_platform_value's own weight.
# --------------------------------------------------------------------------
def interaction_rule(tier: str, band: RoleBand) -> tuple[str, str]:
    """Returns (recommendation, rule_name). Encodes the user's stated preferences."""
    b = band.value
    if tier == "S" and b in ("R1", "R2"):
        return "Serious Apply", f"S+{b} -> Serious Apply"
    if tier == "S" and b == "R3":
        return "Serious Apply", f"S+{b} -> Serious Apply (platform compensates)"
    if tier == "A" and b == "R1":
        return "Serious Apply", f"A+{b} -> Serious Apply"
    if tier == "A" and b == "R2":
        return "High-Priority Review", f"A+{b} -> Serious Apply / High-Priority Review"
    if b == "R4":
        return "Skip / Manual", f"{tier}+R4 -> low transferability, low priority"
    if tier in ("B", "C") and b == "R1":
        return "Apply / Research Company", f"{tier}+{b} -> competes on role & team evidence"
    return "Manual Review", f"{tier}+{b} -> manual review"


def compute_priority(
    *,
    gate: GateResult,
    company: CompanyIntelligence,
    role: RoleClassification,
    fit: FitBreakdown,
    description: str | None,
    profile: RankingProfile,
    freshness: float = 0.5,
    source_status: str = "open",
    application_deadline: datetime | None = None,
    effort_minutes: int = 20,
) -> PriorityResult:
    """Compose the six scores into an Application Priority (0..100).

    No tier bonus, no priority floor. Weights sum to 1.0 across all six
    dimensions (see app/ranking/modes.py), so this is a plain weighted sum —
    no normalization dance needed, unlike the previous version where
    opportunity_estimate conditionally participated.
    """
    w = profile.weights

    cpv = ScoreWithCoverage(
        known_evidence=company.known_evidence_score,
        coverage=company.evidence_coverage,
        conservative=company.conservative_score,
        notes=company.notes,
    )

    rsv_full = compute_role_strategic_value(role, description)
    rsv = ScoreWithCoverage(rsv_full.score, rsv_full.coverage,
                            round(rsv_full.score * rsv_full.coverage
                                  + 50 * (1 - rsv_full.coverage), 2))

    fit_score = ScoreWithCoverage(
        known_evidence=round(fit.known_evidence_score * 100, 2),
        coverage=fit.coverage,
        conservative=round(fit.conservative_score * 100, 2),
    )

    team = compute_team_quality(description)
    career_opt = compute_career_optionality(role, company, description)
    opp_viability = compute_opportunity_viability(
        freshness, source_status, application_deadline, description)
    action_urgency = compute_action_urgency(application_deadline)

    contributions: dict[str, float] = {}
    priority = 0.0
    for name, weight, value in (
        ("company_platform_value", w.company_platform_value, cpv.conservative),
        ("role_strategic_value", w.role_strategic_value, rsv.conservative),
        ("team_project_quality", w.team_project_quality, team.conservative),
        ("current_candidate_fit", w.current_candidate_fit, fit_score.conservative),
        ("career_optionality", w.career_optionality, career_opt.conservative),
        ("opportunity_viability", w.opportunity_viability, opp_viability.conservative),
    ):
        contributions[name] = round(weight * value, 2)
        priority += weight * value

    recommendation, rule = interaction_rule(company.system_tier, role.band)

    # --- Gate overrides everything ---
    if gate.gate is Gate.FAIL:
        priority = min(priority, 5.0)
        recommendation = "Skip (ineligible)"
        rule = "Eligibility FAIL overrides all bonuses"
    elif gate.gate is Gate.REVIEW:
        recommendation = "Manual Review"
        rule = "Eligibility REVIEW -> manual review queue (forced)"

    priority = max(0.0, min(100.0, priority))

    # --- Explanations ---
    why: list[str] = []
    why_not: list[str] = []
    unknowns: list[str] = []

    if company.system_tier in ("S", "A"):
        why.append(
            f"{company.display_tier}-tier platform "
            f"(platform value {cpv.conservative:.0f})"
        )
    if role.band in (RoleBand.R1, RoleBand.R2):
        why.append(f"{role.band.value} role ({role.role_type}) — high transferability")
    if fit.matched_required:
        why.append("matches required: " + ", ".join(fit.matched_required[:4]))
    if "support/reporting-shaped language detected" not in team.notes and team.conservative > 60:
        why.append("evidence of substantial, owned work")

    if fit.missing_required:
        why_not.append("missing required: " + ", ".join(fit.missing_required[:4]))
    if role.band is RoleBand.R3:
        why_not.append("adjacent role — lower direct technical depth")
    if role.band is RoleBand.R4:
        why_not.append("low transferability role — direction weakly aligned")
    if team.notes:
        why_not.extend(team.notes)
    if company.provisional:
        why_not.append(
            f"company evidence incomplete ({company.evidence_coverage:.0%} coverage)"
        )
    if company.risk and company.risk.level.value in ("elevated", "high"):
        why_not.append(
            f"risk radar: {company.risk.level.value} "
            f"({company.risk.signal_count} anonymous signals — not scored)"
        )

    if company.risk and company.risk.manual_research_required:
        unknowns.append("risk signals warrant manual research")
    if company.rating_status in ("unrated", "provisional"):
        unknowns.append("company platform evidence insufficient — needs research")
    if role.needs_review:
        unknowns.append("role classification needs review (thin JD evidence)")
    unknowns.extend(gate.unknowns)

    overall_coverage = round(
        (company.evidence_coverage + fit.coverage + rsv_full.coverage
         + team.coverage + career_opt.coverage + opp_viability.coverage) / 6,
        4,
    )

    return PriorityResult(
        eligibility=gate,
        company_platform_value=cpv,
        role_strategic_value=rsv,
        team_project_quality=team,
        current_candidate_fit=fit_score,
        career_optionality=career_opt,
        opportunity_viability=opp_viability,
        contributions=contributions,
        application_priority=round(priority, 1),
        action_urgency=action_urgency,
        application_effort_minutes=effort_minutes,
        role_band=role.band.value,
        role_type=role.role_type,
        company_tier=company.system_tier,
        company_tier_display=company.display_tier,
        evidence_coverage=overall_coverage,
        freshness=freshness,
        recommendation=recommendation,
        interaction_rule=rule,
        transferability=role.transferability,
        why=why,
        why_not=why_not,
        unknowns=unknowns,
    )
