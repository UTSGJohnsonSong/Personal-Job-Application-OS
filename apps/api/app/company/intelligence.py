"""Company intelligence: graded evidence -> dimension scores -> bounded tiers.

Hard rule (docs/COMPANY_INTELLIGENCE.md): a tier is NEVER produced from model
impressions ("Amazon is famous therefore S"). Every dimension score must be
backed by evidence rows, and the resulting tier is bounded by Evidence Coverage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class SourceGrade(StrEnum):
    A = "A"  # official / regulatory / academic — primary factual source
    B = "B"  # credible secondary
    C = "C"  # anonymous / social — RISK FLAGS ONLY

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


# Company Platform Score sub-weights (docs/COMPANY_TIER_SYSTEM.md).
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


@dataclass
class Evidence:
    url: str
    source_type: str
    grade: SourceGrade
    supports_dimension: CompanyDimension
    summary: str
    value: float | None          # 0..1 observation; None = risk flag only
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
class CompanyIntelligence:
    known_evidence_score: float    # 0..100
    evidence_coverage: float       # 0..1
    conservative_score: float      # 0..100
    dimensions: list[DimensionResult]
    system_tier: str               # S/A/B/C/D
    tier_status: str               # unrated | provisional | medium | high
    provisional: bool
    risk_flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def display_tier(self) -> str:
        """Provisional tiers render with a '?' — never as a settled fact."""
        if self.tier_status == "unrated":
            return "Unrated"
        return f"{self.system_tier}?" if self.provisional else self.system_tier


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


def _aggregate_dimension(
    dim: CompanyDimension, evidence: list[Evidence]
) -> DimensionResult:
    """Grade-weighted aggregation. Grade C never contributes an observation."""
    usable = [
        e for e in evidence
        if e.supports_dimension is dim and e.still_valid
        and e.value is not None and e.grade is not SourceGrade.C
    ]
    if not usable:
        # Genuinely unknown: score=None, confidence=0 (docs/EVIDENCE_COVERAGE.md).
        return DimensionResult(dim, None, 0.0, 0, [])

    num = sum(e.grade.weight * (e.value or 0.0) for e in usable)
    den = sum(e.grade.weight for e in usable)
    score = num / den

    # Confidence grows with evidence volume, capped by the best grade available.
    # A single authoritative (grade-A) source is already fairly reliable for one
    # dimension; corroboration adds the rest. Grade B/C scale it down.
    best = max(e.grade.weight for e in usable)
    confidence = min(1.0, best * (0.85 + 0.05 * (len(usable) - 1)))

    return DimensionResult(
        dimension=dim, score=round(score, 4), confidence=round(confidence, 4),
        evidence_count=len(usable),
        top_evidence=[e.summary for e in usable[:3]],
    )


def assess_company(
    evidence: list[Evidence], *, neutral_prior: float = 0.5
) -> CompanyIntelligence:
    """Compute platform score, coverage and a coverage-bounded tier."""
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
    # The tier is derived from the CONSERVATIVE score, so thin evidence cannot
    # manufacture a high tier out of a couple of positive data points.
    tier = score_to_tier(conservative * 100)

    risk_flags = [
        f"[{e.grade.value}] {e.summary}"
        for e in evidence
        if e.grade is SourceGrade.C and e.still_valid
    ]

    notes: list[str] = []
    if status == "unrated":
        notes.append("Evidence coverage below 40% — needs research; tier not rated.")
    elif status == "provisional":
        notes.append("Provisional tier: evidence coverage 40–64%.")

    # Formal S requires >=2 independent evidence types, >=1 grade-A, coverage>=0.80.
    if tier == "S":
        grades = {e.grade for e in evidence if e.still_valid and e.value is not None}
        types = {e.source_type for e in evidence if e.still_valid and e.value is not None}
        if SourceGrade.A not in grades or len(types) < 2 or coverage < 0.80:
            tier = "A"
            notes.append(
                "S-tier requirements not met (needs ≥2 evidence types, ≥1 grade-A "
                "source, coverage ≥80%); capped at A."
            )

    return CompanyIntelligence(
        known_evidence_score=round(known * 100, 2),
        evidence_coverage=round(coverage, 4),
        conservative_score=round(conservative * 100, 2),
        dimensions=dims,
        system_tier=tier,
        tier_status=status,
        provisional=status in ("unrated", "provisional"),
        risk_flags=risk_flags,
        notes=notes,
    )
