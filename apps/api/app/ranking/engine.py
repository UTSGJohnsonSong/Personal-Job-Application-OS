from __future__ import annotations

from dataclasses import dataclass, field

from app.eligibility.engine import EligibilityReport, Verdict
from app.parsing.jd_parser import ParsedJD

# Explainable hybrid scoring. No opaque LLM total: the score is a transparent
# weighted sum of per-dimension sub-scores, each with evidence + confidence.
# Reproducible: same inputs + same weights => same output. See docs/RANKING_ENGINE.md.

DEFAULT_WEIGHTS: dict[str, float] = {
    "hard_eligibility": 3.0,
    "skill_match": 2.5,
    "role_direction": 2.0,
    "location_mode": 1.5,
    "compensation": 1.0,
    "freshness": 1.0,
    "company_quality": 0.8,
    "application_cost": 0.7,
    "historical_outcome": 1.5,
}


@dataclass
class Evidence:
    polarity: str  # positive/negative
    text: str
    origin: str = "system"  # jd/context/system


@dataclass
class DimensionScore:
    name: str
    score: float  # 0..1
    weight: float
    confidence: float
    uncertainty: str = ""
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class RankInputs:
    jd: ParsedJD
    eligibility: EligibilityReport
    candidate_skills: set[str]
    jd_skills: set[str]
    target_roles: set[str]
    normalized_title: str
    remote_mode: str | None
    preferred_remote: str | None  # remote/hybrid/onsite/any
    location_ok: bool | None
    salary_ok: bool | None
    freshness_score: float
    company_quality: float | None  # 0..1 or None
    estimated_minutes: int
    historical_outcome_rate: float | None  # observed reply/interview rate for similar


@dataclass
class RankResult:
    total_score: float
    confidence: float
    strategy: str  # quick/serious/manual
    dimensions: list[DimensionScore]
    why_recommended: list[str]
    why_not: list[str]
    suggested_minutes: int


_VERDICT_SCORE = {
    Verdict.ELIGIBLE: 1.0,
    Verdict.LIKELY_ELIGIBLE: 0.8,
    Verdict.UNCERTAIN: 0.5,
    Verdict.LIKELY_INELIGIBLE: 0.2,
    Verdict.INELIGIBLE: 0.0,
}


def _score_eligibility(inp: RankInputs) -> DimensionScore:
    s = _VERDICT_SCORE[inp.eligibility.verdict]
    ev = [Evidence("positive" if s >= 0.8 else "negative", r, "jd")
          for r in inp.eligibility.reasons[:3]]
    conf = 0.9 if inp.eligibility.verdict != Verdict.UNCERTAIN else 0.5
    unc = "eligibility uncertain" if inp.eligibility.verdict == Verdict.UNCERTAIN else ""
    return DimensionScore("hard_eligibility", s, DEFAULT_WEIGHTS["hard_eligibility"], conf, unc, ev)


def _score_skills(inp: RankInputs) -> DimensionScore:
    if not inp.jd_skills:
        return DimensionScore("skill_match", 0.5, DEFAULT_WEIGHTS["skill_match"], 0.3,
                              "no skills detected in JD")
    overlap = inp.candidate_skills & inp.jd_skills
    s = len(overlap) / len(inp.jd_skills)
    ev = (
        [Evidence("positive", f"matches: {', '.join(sorted(overlap))}", "context")]
        if overlap
        else []
    )
    missing = inp.jd_skills - inp.candidate_skills
    if missing:
        ev.append(Evidence("negative", f"missing: {', '.join(sorted(missing))}", "jd"))
    return DimensionScore("skill_match", s, DEFAULT_WEIGHTS["skill_match"], 0.7, "", ev)


def _score_role(inp: RankInputs) -> DimensionScore:
    if not inp.target_roles:
        return DimensionScore("role_direction", 0.5, DEFAULT_WEIGHTS["role_direction"], 0.3,
                              "no target roles set")
    title = inp.normalized_title
    hit = any(role.lower() in title for role in inp.target_roles)
    s = 1.0 if hit else 0.25
    ev = [Evidence("positive" if hit else "negative",
                   f"title '{title}' vs targets {sorted(inp.target_roles)}", "jd")]
    return DimensionScore("role_direction", s, DEFAULT_WEIGHTS["role_direction"], 0.6, "", ev)


def _score_location(inp: RankInputs) -> DimensionScore:
    pref = inp.preferred_remote
    if pref in (None, "any"):
        s, conf = 0.7, 0.4
        ev = [Evidence("positive", "no strict location/mode preference", "context")]
    elif inp.remote_mode and pref == inp.remote_mode:
        s, conf, ev = 1.0, 0.8, [Evidence("positive", f"mode {inp.remote_mode} matches", "jd")]
    elif inp.location_ok:
        s, conf, ev = 0.8, 0.6, [Evidence("positive", "location acceptable", "context")]
    elif inp.location_ok is False:
        s, conf, ev = 0.1, 0.7, [Evidence("negative", "location/mode mismatch", "jd")]
    else:
        s, conf, ev = 0.5, 0.3, [Evidence("negative", "location unknown", "jd")]
    return DimensionScore("location_mode", s, DEFAULT_WEIGHTS["location_mode"], conf,
                          "" if conf > 0.4 else "location uncertain", ev)


def _simple(name: str, value: float | None, default: float, conf: float, pos: str, neg: str):
    if value is None:
        return DimensionScore(name, default, DEFAULT_WEIGHTS[name], 0.3, f"{name} unknown")
    ev = [Evidence("positive" if value >= 0.5 else "negative", pos if value >= 0.5 else neg)]
    return DimensionScore(name, value, DEFAULT_WEIGHTS[name], conf, "", ev)


def rank(inp: RankInputs, weights: dict[str, float] | None = None) -> RankResult:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    dims = [
        _score_eligibility(inp),
        _score_skills(inp),
        _score_role(inp),
        _score_location(inp),
        _simple("compensation", inp.salary_ok if inp.salary_ok is None else float(inp.salary_ok),
                0.5, 0.6, "meets comp preference", "below comp preference"),
        _simple("freshness", inp.freshness_score, 0.5, 0.9, "fresh posting", "stale posting"),
        _simple("company_quality", inp.company_quality, 0.5, 0.4,
                "known company", "unknown company"),
        _simple("application_cost",
                1.0 - min(inp.estimated_minutes, 60) / 60, 0.5, 0.6,
                "low effort", "high effort"),
        _simple("historical_outcome", inp.historical_outcome_rate, 0.5, 0.5,
                "similar jobs replied", "similar jobs went cold"),
    ]
    # Apply active weights.
    for d in dims:
        d.weight = w.get(d.name, d.weight)

    num = sum(d.weight * d.score * d.confidence for d in dims)
    den = sum(d.weight * d.confidence for d in dims) or 1.0
    total = num / den
    overall_conf = sum(d.confidence for d in dims) / len(dims)

    # Hard gate: ineligible caps the score.
    if inp.eligibility.verdict == Verdict.INELIGIBLE:
        total = min(total, 0.15)

    why = [e.text for d in dims for e in d.evidence if e.polarity == "positive"][:4]
    why_not = [e.text for d in dims for e in d.evidence if e.polarity == "negative"][:4]

    if inp.eligibility.verdict in (Verdict.UNCERTAIN, Verdict.LIKELY_INELIGIBLE) or \
            inp.eligibility.needs_user_confirmation:
        strategy = "manual"
    elif total >= 0.72:
        strategy = "serious"
    elif total >= 0.5:
        strategy = "quick"
    else:
        strategy = "manual"

    suggested = 25 if strategy == "serious" else (8 if strategy == "quick" else 15)

    return RankResult(
        total_score=round(total, 4),
        confidence=round(overall_conf, 4),
        strategy=strategy,
        dimensions=dims,
        why_recommended=why,
        why_not=why_not,
        suggested_minutes=suggested,
    )
