from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.parsing.jd_parser import ParsedJD


class Verdict(StrEnum):
    ELIGIBLE = "eligible"
    LIKELY_ELIGIBLE = "likely_eligible"
    UNCERTAIN = "uncertain"
    LIKELY_INELIGIBLE = "likely_ineligible"
    INELIGIBLE = "ineligible"


@dataclass
class CandidateFacts:
    """ONLY confirmed, application-usable facts should be passed here.

    Fields left None mean "unknown" — the engine must not guess.
    """

    highest_degree: str | None = None  # phd/masters/bachelors/associate
    degree_rank: int | None = None  # helper: phd=4..associate=1
    work_auth_countries: set[str] = field(default_factory=set)
    needs_sponsorship: bool | None = None
    target_employment_types: set[str] = field(default_factory=set)
    years_experience: float | None = None


@dataclass
class CheckOutcome:
    name: str
    outcome: str  # pass/fail/unknown
    is_hard: bool
    evidence_jd: str = ""
    evidence_context: str = ""
    detail: str = ""


@dataclass
class EligibilityReport:
    verdict: Verdict
    reasons: list[str] = field(default_factory=list)
    jd_evidence: list[str] = field(default_factory=list)
    context_evidence: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    needs_user_confirmation: bool = False
    checks: list[CheckOutcome] = field(default_factory=list)


_DEGREE_RANK = {"associate": 1, "bachelors": 2, "masters": 3, "phd": 4}


def _check_sponsorship(jd: ParsedJD, facts: CandidateFacts) -> CheckOutcome | None:
    if jd.needs_sponsorship_info != "no_sponsorship":
        return None
    ev = next((r.evidence for r in jd.requirements if r.field == "sponsorship"), "")
    if facts.needs_sponsorship is None:
        return CheckOutcome("sponsorship", "unknown", True, ev, "", "sponsorship need unknown")
    if facts.needs_sponsorship:
        return CheckOutcome(
            "sponsorship", "fail", True, ev,
            "candidate needs sponsorship", "JD states no sponsorship"
        )
    return CheckOutcome("sponsorship", "pass", True, ev, "no sponsorship needed")


def _check_degree(jd: ParsedJD, facts: CandidateFacts) -> CheckOutcome | None:
    if not jd.degree_level:
        return None
    ev = next((r.evidence for r in jd.requirements if r.field == "degree"), "")
    required_rank = _DEGREE_RANK.get(jd.degree_level)
    have = facts.degree_rank or (
        _DEGREE_RANK.get(facts.highest_degree) if facts.highest_degree else None
    )
    if required_rank is None or have is None:
        return CheckOutcome("degree", "unknown", True, ev, "", "degree unknown")
    if have >= required_rank:
        return CheckOutcome("degree", "pass", True, ev, f"has {facts.highest_degree}")
    return CheckOutcome(
        "degree", "fail", True, ev, f"has {facts.highest_degree}",
        f"requires {jd.degree_level}"
    )


def _check_employment_type(jd: ParsedJD, facts: CandidateFacts) -> CheckOutcome | None:
    if not jd.employment_type:
        return None
    ev = next((r.evidence for r in jd.requirements if r.field == "employment_type"), "")
    if not facts.target_employment_types:
        return CheckOutcome("employment_type", "unknown", False, ev, "", "no target set")
    if jd.employment_type in facts.target_employment_types:
        return CheckOutcome("employment_type", "pass", False, ev, "matches target")
    return CheckOutcome(
        "employment_type", "fail", False, ev,
        f"targets {sorted(facts.target_employment_types)}",
        f"job is {jd.employment_type}"
    )


def evaluate(jd: ParsedJD, facts: CandidateFacts) -> EligibilityReport:
    """Deterministic aggregation. See docs/ELIGIBILITY_ENGINE.md."""
    checks = [
        c
        for c in (
            _check_sponsorship(jd, facts),
            _check_degree(jd, facts),
            _check_employment_type(jd, facts),
        )
        if c is not None
    ]

    report = EligibilityReport(verdict=Verdict.ELIGIBLE, checks=checks)
    hard_fail_strong = False
    hard_fail_weak = False
    hard_unknown = False

    for c in checks:
        if c.evidence_jd:
            report.jd_evidence.append(c.evidence_jd)
        if c.evidence_context:
            report.context_evidence.append(c.evidence_context)
        if c.outcome == "fail":
            report.reasons.append(f"{c.name}: {c.detail}")
            report.conflicts.append(f"{c.name}: {c.evidence_context} vs {c.detail}")
            if c.is_hard:
                # Strong evidence when we have a concrete conflicting fact.
                if c.evidence_context:
                    hard_fail_strong = True
                else:
                    hard_fail_weak = True
        elif c.outcome == "unknown":
            report.unknowns.append(f"{c.name}: {c.detail}")
            if c.is_hard:
                hard_unknown = True
        else:
            report.reasons.append(f"{c.name}: ok")

    if hard_fail_strong:
        report.verdict = Verdict.INELIGIBLE
    elif hard_fail_weak:
        report.verdict = Verdict.LIKELY_INELIGIBLE
    elif hard_unknown:
        report.verdict = Verdict.UNCERTAIN
        report.needs_user_confirmation = True
    elif report.unknowns:
        report.verdict = Verdict.LIKELY_ELIGIBLE
    else:
        report.verdict = Verdict.ELIGIBLE

    return report
