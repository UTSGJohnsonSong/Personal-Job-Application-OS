"""Company intelligence: graded evidence -> dimension scores -> two INDEPENDENT axes.

Hard rule (docs/COMPANY_INTELLIGENCE.md): a tier is NEVER produced from model
impressions ("Amazon is famous therefore S").

Two axes that must not be conflated:
  1. `estimated_tier`  — derived from the evidence SCORE
  2. `rating_status`   — derived from Evidence COVERAGE
A company can legitimately be "Estimated Tier: S?, Status: Provisional, 52%".
Coverage never rewrites the letter; it qualifies how much to trust it.

Grade-C (anonymous) evidence never touches the platform score, but it is not
discarded either — it feeds an independent Risk Score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum


class SourceGrade(StrEnum):
    A = "A"  # official / regulatory / academic — primary factual source
    B = "B"  # credible secondary
    C = "C"  # anonymous / social — risk signal only, never platform score

    @property
    def weight(self) -> float:
        return {"A": 1.0, "B": 0.6, "C": 0.25}[self.value]


class CompanyDimension(StrEnum):
    BRAND_SIGNAL = "resume_brand_signal"
    TECHNICAL_DENSITY = "technical_density"
    INTERNSHIP_PROGRAM = "internship_program_quality"
    CAREER_OPTIONALITY = "career_optionality"
    SYSTEM_SCALE = "system_project_scale"
    TALENT_NETWORK = "talent_network"
    STABILITY = "stability"


PLATFORM_WEIGHTS: dict[CompanyDimension, float] = {
    CompanyDimension.BRAND_SIGNAL: 0.30,
    CompanyDimension.TECHNICAL_DENSITY: 0.20,
    CompanyDimension.INTERNSHIP_PROGRAM: 0.15,
    CompanyDimension.CAREER_OPTIONALITY: 0.15,
    CompanyDimension.SYSTEM_SCALE: 0.10,
    CompanyDimension.TALENT_NETWORK: 0.05,
    CompanyDimension.STABILITY: 0.05,
}

TIER_BANDS = [(88, "S"), (76, "A"), (62, "B"), (45, "C"), (0, "D")]


class RiskLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    ELEVATED = "elevated"
    HIGH = "high"


@dataclass
class Evidence:
    url: str
    source_type: str
    grade: SourceGrade
    supports_dimension: CompanyDimension
    summary: str
    value: float | None          # 0..1 observation; None = qualitative flag
    fetched_at: datetime | None = None
    published_at: datetime | None = None
    still_valid: bool = True


@dataclass
class DimensionResult:
    dimension: CompanyDimension
    score: float | None          # None => genuinely unknown
    confidence: float            # 0 => unknown; never a fake prior
    evidence_count: int
    top_evidence: list[str] = field(default_factory=list)
    is_prior: bool = False


@dataclass
class RiskAssessment:
    """Independent of the platform score. Anonymous signal has a radar, not a vote."""

    level: RiskLevel
    evidence_quality: str        # low | medium
    signal_count: int
    independent_sources: int
    manual_research_required: bool
    flags: list[str] = field(default_factory=list)


@dataclass
class CompanyIntelligence:
    # --- axis 1: score ---
    known_evidence_score: float    # 0..100, from observed evidence only
    conservative_score: float      # 0..100, shrunk toward prior by coverage
    estimated_tier: str            # letter derived from the SCORE axis
    # --- axis 2: coverage ---
    evidence_coverage: float       # 0..1
    rating_status: str             # unrated | provisional | medium | high
    # --- formal rating: only when both axes qualify ---
    rated_tier: str | None         # None while provisional/unrated
    dimensions: list[DimensionResult] = field(default_factory=list)
    risk: RiskAssessment | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def provisional(self) -> bool:
        return self.rating_status in ("unrated", "provisional")

    @property
    def display_tier(self) -> str:
        """`S?` means 'evidence points to S but coverage is thin' — not 'B'."""
        if self.rating_status == "unrated":
            return f"{self.estimated_tier}? (unrated)"
        return f"{self.estimated_tier}?" if self.provisional else self.estimated_tier

    @property
    def system_tier(self) -> str:
        """Back-compat alias used by scoring; prefers the formal rating."""
        return self.rated_tier or self.estimated_tier


def coverage_status(coverage: float) -> str:
    if coverage < 0.40:
        return "unrated"
    if coverage < 0.65:
        return "provisional"
    if coverage < 0.80:
        return "medium"
    return "high"


def score_to_tier(score: float) -> str:
    for threshold, tier in TIER_BANDS:
        if score >= threshold:
            return tier
    return "D"


def _aggregate_dimension(dim: CompanyDimension, evidence: list[Evidence]) -> DimensionResult:
    """Grade-weighted aggregation. Grade C never contributes an observation."""
    usable = [
        e for e in evidence
        if e.supports_dimension is dim and e.still_valid
        and e.value is not None and e.grade is not SourceGrade.C
    ]
    if not usable:
        return DimensionResult(dim, None, 0.0, 0, [])

    num = sum(e.grade.weight * (e.value or 0.0) for e in usable)
    den = sum(e.grade.weight for e in usable)
    best = max(e.grade.weight for e in usable)
    confidence = min(1.0, best * (0.85 + 0.05 * (len(usable) - 1)))

    return DimensionResult(
        dimension=dim, score=round(num / den, 4), confidence=round(confidence, 4),
        evidence_count=len(usable), top_evidence=[e.summary for e in usable[:3]],
    )


def assess_risk(evidence: list[Evidence], *, now: datetime | None = None) -> RiskAssessment:
    """Grade-C signal becomes an independent risk radar.

    Never lowers the platform score or the tier. Many consistent, recent,
    independent negative signals escalate to `manual_research_required`.
    """
    now = now or datetime.now(UTC)
    recent_cutoff = now - timedelta(days=540)

    negatives = [
        e for e in evidence
        if e.grade is SourceGrade.C and e.still_valid
        and (e.value is None or e.value < 0.4)
    ]
    recent = [
        e for e in negatives
        if e.published_at is None or e.published_at >= recent_cutoff
    ]
    sources = {e.source_type for e in recent}

    n, s = len(recent), len(sources)
    if n == 0:
        level = RiskLevel.NONE
    elif n >= 3 and s >= 2:
        level = RiskLevel.HIGH
    elif n >= 2:
        level = RiskLevel.ELEVATED
    else:
        level = RiskLevel.LOW

    return RiskAssessment(
        level=level,
        evidence_quality="low" if s < 2 else "medium",
        signal_count=n,
        independent_sources=s,
        # Consistent + recent + independent => go look properly. Not a demotion.
        manual_research_required=(n >= 3 and s >= 2),
        flags=[f"[C/{e.source_type}] {e.summary}" for e in negatives[:5]],
    )


def assess_company(
    evidence: list[Evidence], *, neutral_prior: float = 0.5
) -> CompanyIntelligence:
    dims = [_aggregate_dimension(d, evidence) for d in CompanyDimension]

    num = 0.0
    den_conf = 0.0
    den_total = 0.0
    for d in dims:
        w = PLATFORM_WEIGHTS[d.dimension]
        den_total += w
        if d.score is not None and d.confidence > 0:
            num += w * d.score * d.confidence
            den_conf += w * d.confidence

    known = (num / den_conf) if den_conf else 0.0
    coverage = (den_conf / den_total) if den_total else 0.0
    conservative = known * coverage + neutral_prior * (1 - coverage)

    status = coverage_status(coverage)
    # AXIS 1: the letter comes from the evidence score, NOT from coverage.
    estimated = score_to_tier(known * 100) if den_conf else "D"

    notes: list[str] = []
    # A formal rating additionally requires sufficient coverage.
    rated: str | None = None
    if status in ("medium", "high"):
        rated = estimated
        if estimated == "S":
            grades = {e.grade for e in evidence if e.still_valid and e.value is not None}
            types = {e.source_type for e in evidence if e.still_valid and e.value is not None}
            if SourceGrade.A not in grades or len(types) < 2 or coverage < 0.80:
                rated = "A"
                notes.append(
                    "Formal S requires ≥2 evidence types, ≥1 grade-A source and "
                    "coverage ≥80%; formal rating capped at A."
                )
    else:
        notes.append(
            f"Provisional: evidence coverage {coverage:.0%}. "
            "Estimated tier reflects the evidence found so far, not a formal rating."
        )
    if status == "unrated":
        notes.append("Coverage below 40% — needs research.")

    risk = assess_risk(evidence)
    if risk.manual_research_required:
        notes.append(
            f"Risk radar: {risk.signal_count} recent negative signals across "
            f"{risk.independent_sources} sources — manual research required "
            "(does not change the tier)."
        )

    return CompanyIntelligence(
        known_evidence_score=round(known * 100, 2),
        conservative_score=round(conservative * 100, 2),
        estimated_tier=estimated,
        evidence_coverage=round(coverage, 4),
        rating_status=status,
        rated_tier=rated,
        dimensions=dims,
        risk=risk,
        notes=notes,
    )
