"""Application Priority — six independent scores, never one "match %".

Replaces the single 0..1 Match Score. Eligibility is a gate (app/ranking/gate.py),
not a weighted dimension. Freshness and effort only reorder; they never make a
bad job good.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
    score: float
    coverage: float
    career_transferability: float
    technical_depth: float
    production_responsibility: float
    long_term_direction: float
    title_readability: float
    evidence: list[str] = field(default_factory=list)


@dataclass
class PriorityResult:
    # --- gate ---
    eligibility: GateResult
    # --- six independent scores (0..100) ---
    company_platform_value: ScoreWithCoverage
    role_strategic_value: ScoreWithCoverage
    current_candidate_fit: ScoreWithCoverage
    team_project_quality: ScoreWithCoverage
    career_optionality: ScoreWithCoverage
    application_priority: float                  # 0..100, NOT a match %
    # --- context ---
    role_band: str
    role_type: str
    company_tier: str
    company_tier_display: str
    evidence_coverage: float
    opportunity_estimate: str                    # text; no fake number
    freshness: float
    effort_minutes: int
    recommendation: str                          # Serious Apply / ... / Skip
    interaction_rule: str
    platform_multiplier: float
    transferability: float
    why: list[str] = field(default_factory=list)
    why_not: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    formula_version: str = "v2"

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
            "evidence_coverage": self.evidence_coverage,
            "opportunity_estimate": self.opportunity_estimate,
            "application_priority": self.application_priority,
            "recommendation": self.recommendation,
            "interaction_rule": self.interaction_rule,
            "why": self.why,
            "why_not": self.why_not,
            "unknowns": self.unknowns,
            "formula_version": self.formula_version,
        }


# --------------------------------------------------------------------------
# Role Strategic Value (docs/INTERNSHIP_RANKING.md §13)
# --------------------------------------------------------------------------
_RSV_WEIGHTS = {
    "career_transferability": 0.30,
    "technical_depth": 0.25,
    "production_responsibility": 0.20,
    "long_term_direction": 0.15,
    "title_readability": 0.10,
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
    "unknown": 0.3,
}


def compute_role_strategic_value(
    role: RoleClassification, description: str | None
) -> RoleStrategicValue:
    """Strategic value of the ROLE ITSELF, independent of the user's current skills."""
    body = (description or "").lower()

    transferability = role.transferability
    depth = role.technical_density
    # Production responsibility: evidence of shipping real things.
    prod_signals = ["production", "deploy", "launch", "real users", "ship",
                    "on-call", "scale", "end-to-end", "own"]
    hits = sum(1 for s in prod_signals if s in body)
    production = min(1.0, hits / 4.0) if body else 0.0
    direction = _DIRECTION_ALIGNMENT.get(role.role_type, 0.3)
    # Title readability: how easily a recruiter reads the experience.
    readability = 0.9 if role.band in (RoleBand.R1, RoleBand.R2) else (
        0.6 if role.band is RoleBand.R3 else 0.3
    )

    parts = {
        "career_transferability": transferability,
        "technical_depth": depth,
        "production_responsibility": production,
        "long_term_direction": direction,
        "title_readability": readability,
    }
    score = sum(_RSV_WEIGHTS[k] * v for k, v in parts.items())
    # Coverage: we can only judge depth/production if we actually have a JD body.
    coverage = 0.55 if not body else min(1.0, 0.7 + 0.3 * role.confidence)

    return RoleStrategicValue(
        score=round(score * 100, 2),
        coverage=round(coverage, 4),
        career_transferability=round(transferability, 3),
        technical_depth=round(depth, 3),
        production_responsibility=round(production, 3),
        long_term_direction=round(direction, 3),
        title_readability=readability,
        evidence=role.evidence,
    )


def compute_team_quality(description: str | None) -> ScoreWithCoverage:
    """Is the actual work real, owned and tellable in an interview?"""
    body = (description or "").lower()
    if not body:
        return ScoreWithCoverage(None, 0.0, 50.0, is_prior=True,
                                 notes=["no job description available"])
    signals = ["team", "mentor", "project", "own", "design", "build",
               "collaborate", "code review", "production", "impact"]
    hits = sum(1 for s in signals if s in body)
    score = min(1.0, hits / 7.0)
    coverage = min(1.0, 0.4 + 0.06 * len(body) / 100)
    conservative = score * coverage + 0.5 * (1 - coverage)
    return ScoreWithCoverage(round(score * 100, 2), round(coverage, 4),
                             round(conservative * 100, 2))


# --------------------------------------------------------------------------
# Tier x Role interaction rules
# --------------------------------------------------------------------------
def interaction_rule(tier: str, band: RoleBand) -> tuple[str, str]:
    """Returns (recommendation, rule_name). Encodes the user's stated preferences."""
    b = band.value
    if tier == "S" and b in ("R1", "R2"):
        return "Serious Apply", f"S+{b} → Serious Apply"
    if tier == "S" and b == "R3":
        return "Serious Apply", f"S+{b} → Serious Apply (platform compensates)"
    if tier == "A" and b == "R1":
        return "Serious Apply", f"A+{b} → Serious Apply"
    if tier == "A" and b == "R2":
        return "High-Priority Review", f"A+{b} → Serious Apply / High-Priority Review"
    if b == "R4":
        return "Skip / Manual", f"{tier}+R4 → platform bonus heavily damped"
    if tier in ("B", "C") and b == "R1":
        return "Apply / Research Company", f"{tier}+R1 → competes on role & team evidence"
    return "Manual Review", f"{tier}+{b} → manual review"


def compute_priority(
    *,
    gate: GateResult,
    company: CompanyIntelligence,
    role: RoleClassification,
    fit: FitBreakdown,
    description: str | None,
    profile: RankingProfile,
    freshness: float = 0.5,
    effort_minutes: int = 20,
    has_outcome_history: bool = False,
    deadline_within_72h: bool = False,
) -> PriorityResult:
    """Compose the six scores into an Application Priority (0..100)."""
    w = profile.weights

    # --- 1. Company Platform Value ---
    cpv = ScoreWithCoverage(
        known_evidence=company.known_evidence_score,
        coverage=company.evidence_coverage,
        conservative=company.conservative_score,
        notes=company.notes,
    )

    # --- 2. Role Strategic Value ---
    rsv_full = compute_role_strategic_value(role, description)
    rsv = ScoreWithCoverage(rsv_full.score, rsv_full.coverage,
                            round(rsv_full.score * rsv_full.coverage
                                  + 50 * (1 - rsv_full.coverage), 2))

    # --- 3. Current Candidate Fit (evidence-weighted, from skill ontology) ---
    fit_score = ScoreWithCoverage(
        known_evidence=round(fit.known_evidence_score * 100, 2),
        coverage=fit.coverage,
        conservative=round(fit.conservative_score * 100, 2),
    )

    # --- 4. Team / Project Quality ---
    team = compute_team_quality(description)

    # --- 5. Career Optionality ---
    opt_raw = 0.6 * (company.conservative_score / 100) + 0.4 * role.transferability
    career_opt = ScoreWithCoverage(
        round(opt_raw * 100, 2), company.evidence_coverage,
        round((opt_raw * company.evidence_coverage
               + 0.5 * (1 - company.evidence_coverage)) * 100, 2),
    )

    # --- Opportunity estimate: no fake numbers before real outcome data ---
    opportunity_text = (
        "Insufficient Personal Outcome Data" if not has_outcome_history
        else "Estimated from personal outcome history"
    )
    opportunity_component = 50.0 if not has_outcome_history else 50.0

    # --- Freshness + effort: ordering only, tightly bounded ---
    effort_factor = 1.0 - min(effort_minutes, 60) / 60
    fresh_effort_component = (0.5 * freshness + 0.5 * effort_factor) * 100

    # --- Weighted strategic base ---
    base = (
        w.company_platform_value * cpv.conservative
        + w.role_strategic_value * rsv.conservative
        + w.team_project_quality * team.conservative
        + w.current_candidate_fit * fit_score.conservative
        + w.opportunity_estimate * opportunity_component
        + w.freshness_and_effort * fresh_effort_component
    ) / (w.total() or 1.0)

    # --- Non-linear platform multiplier, damped by role transferability ---
    mult = profile.platform_multiplier.get(company.system_tier, 1.0)
    effective_bonus = (mult - 1.0) * role.transferability
    priority = base * (1.0 + effective_bonus)

    # --- Urgency nudge (ordering only, capped) ---
    if deadline_within_72h:
        priority += 3.0

    # --- Gate overrides everything ---
    recommendation, rule = interaction_rule(company.system_tier, role.band)
    if gate.gate is Gate.FAIL:
        priority = min(priority, 5.0)
        recommendation = "Skip (ineligible)"
        rule = "Eligibility FAIL overrides all bonuses"
    elif gate.gate is Gate.REVIEW:
        recommendation = "Manual Review"
        rule = "Eligibility REVIEW → manual review queue"

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
    if rsv_full.production_responsibility > 0.5:
        why.append("evidence of production responsibility")

    if fit.missing_required:
        why_not.append("missing required: " + ", ".join(fit.missing_required[:4]))
    if role.band is RoleBand.R3:
        why_not.append("adjacent role — lower direct technical depth")
    if role.band is RoleBand.R4:
        why_not.append("low transferability role — platform bonus damped")
    if company.provisional:
        why_not.append(
            f"company evidence incomplete ({company.evidence_coverage:.0%} coverage)"
        )
    for f in company.risk_flags[:2]:
        why_not.append(f"risk flag {f}")

    if company.tier_status in ("unrated", "provisional"):
        unknowns.append("company platform evidence insufficient — needs research")
    if role.needs_review:
        unknowns.append("role classification needs review (thin JD evidence)")
    if not has_outcome_history:
        unknowns.append("no personal outcome history yet")
    unknowns.extend(gate.unknowns)

    overall_coverage = round(
        (company.evidence_coverage + fit.coverage + rsv_full.coverage) / 3, 4
    )

    return PriorityResult(
        eligibility=gate,
        company_platform_value=cpv,
        role_strategic_value=rsv,
        current_candidate_fit=fit_score,
        team_project_quality=team,
        career_optionality=career_opt,
        application_priority=round(priority, 1),
        role_band=role.band.value,
        role_type=role.role_type,
        company_tier=company.system_tier,
        company_tier_display=company.display_tier,
        evidence_coverage=overall_coverage,
        opportunity_estimate=opportunity_text,
        freshness=freshness,
        effort_minutes=effort_minutes,
        recommendation=recommendation,
        interaction_rule=rule,
        platform_multiplier=mult,
        transferability=role.transferability,
        why=why,
        why_not=why_not,
        unknowns=unknowns,
    )
