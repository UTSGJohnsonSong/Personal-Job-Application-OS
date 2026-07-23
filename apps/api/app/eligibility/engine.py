from __future__ import annotations

import re
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
    # The seniority levels the candidate is actually targeting. For a co-op
    # student this is {intern, co_op, new_grad, entry}. Without it the gate had
    # no basis to reject a "Senior Manager, 10+ years" role, which is how such
    # roles reached a student's inbox marked eligible.
    target_seniority: set[str] = field(default_factory=set)


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


def _check_location(location: str | None, facts: CandidateFacts) -> CheckOutcome | None:
    """Can the candidate legally hold a job posted at this location?

    This check was missing entirely. `work_auth_countries` existed on the
    candidate facts and nothing ever compared a posting's location against it,
    so a Canadian PR saw "Eligibility PASS" on roles in Dubai, Brazil and
    Uruguay — the gate was reading only the JD text and never the location.

    "Remote" is not a licence: remote roles are almost always scoped to
    countries where the employer has an entity, and the location string is that
    scope. An unreadable location stays unknown rather than passing.
    """
    if not facts.work_auth_countries:
        return None  # nothing declared; the engine must not guess
    if not location or not location.strip():
        return CheckOutcome(
            name="location", outcome="unknown", is_hard=True,
            detail="posting has no location; cannot confirm work authorisation")

    from app.company.access import LocationClass, classify_location

    cls = classify_location(location)
    authorised_in_canada = {c.upper() for c in facts.work_auth_countries} & {"CA", "CAN"}

    if cls in (LocationClass.CANADA_EXPLICIT, LocationClass.CANADA_REMOTE):
        if authorised_in_canada:
            return CheckOutcome(
                name="location", outcome="pass", is_hard=True,
                evidence_jd=location, detail="posting is in Canada")
        return CheckOutcome(
            name="location", outcome="fail", is_hard=True, evidence_jd=location,
            detail="posting is in Canada and no Canadian work authorisation")

    if cls is LocationClass.CANADA_NOT_ELIGIBLE:
        return CheckOutcome(
            name="location", outcome="fail", is_hard=True, evidence_jd=location,
            detail=f"posting requires authorisation for {location}, which the "
                   "candidate does not hold")

    if cls in (LocationClass.AMERICAS_REMOTE_NEEDS_REVIEW,
               LocationClass.CANADA_POSSIBLE):
        return CheckOutcome(
            name="location", outcome="unknown", is_hard=True,
            evidence_jd=location,
            detail="broad or remote scope; needs a human to confirm Canada is "
                   "included")

    return CheckOutcome(
        name="location", outcome="unknown", is_hard=True, evidence_jd=location,
        detail=f"location {location!r} not recognised as reachable")


# Seniority ladder, low to high. A co-op student targets the bottom rungs;
# anything from "mid" up is out of reach this cycle.
_SENIORITY_ORDER = {
    "intern": 0, "co_op": 0, "new_grad": 1, "entry": 1, "junior": 1,
    "mid": 2, "senior": 3, "staff": 4, "principal": 4, "lead": 3,
    "manager": 4, "director": 5, "vp": 6, "executive": 7,
}
# Title markers. Intern/co-op/new-grad are checked FIRST, because "New Grad
# Software Engineer" and "Senior Software Engineer Intern" must not be read as
# senior. Order matters within this list.
_SENIORITY_MARKERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(intern|internship|co-?op)\b", re.I), "intern"),
    (re.compile(r"\b(new\s?grad|university\s+grad|campus|early\s+career|"
                r"graduate\s+(program|analyst|engineer)|apprentice)\b", re.I), "new_grad"),
    (re.compile(r"\b(junior|jr\.?|entry[-\s]?level|associate)\b", re.I), "junior"),
    (re.compile(r"\b(chief|\bC[EFTOI]O\b|president)\b", re.I), "executive"),
    (re.compile(r"\b(vice\s+president|\bVP\b|\bSVP\b|\bEVP\b|head\s+of)\b", re.I), "vp"),
    (re.compile(r"\b(director)\b", re.I), "director"),
    (re.compile(r"\b(principal|staff|distinguished|architect)\b", re.I), "principal"),
    (re.compile(r"\b(manager|mgr\.?|team\s+lead|tech\s+lead)\b", re.I), "manager"),
    (re.compile(r"\b(senior|sr\.?|lead)\b", re.I), "senior"),
]


def detect_seniority(title: str | None, years_required: float | None = None) -> str | None:
    """A role's seniority from its title.

    Title only. A stated years requirement is deliberately NOT folded in here —
    the experience check owns that, with a gradient (a small overshoot passes, a
    large one fails), so a plain "Data Analyst, 4 years" is a stretch to review
    rather than a hard mid-level rejection. `years_required` is accepted for a
    stable signature and callers that want a combined signal, but is unused.

    Returns None when the title carries no level marker — a plain "Data Analyst"
    — which the gate treats as unknown rather than guessing junior or senior.
    """
    text = title or ""
    for pattern, level in _SENIORITY_MARKERS:
        if pattern.search(text):
            return level
    return None


def _check_seniority(
    seniority: str | None, facts: CandidateFacts
) -> CheckOutcome | None:
    """Is the role at a level the candidate is actually targeting?

    A hard check: a co-op student cannot hold a Senior Manager or Director role
    however much he might want to, so it belongs with work authorisation and
    degree, not with the soft preference signals.
    """
    if not facts.target_seniority or seniority is None:
        return None
    role_rank = _SENIORITY_ORDER.get(seniority)
    if role_rank is None:
        return None
    ceiling = max(_SENIORITY_ORDER.get(s, 0) for s in facts.target_seniority)
    if role_rank <= ceiling:
        return CheckOutcome("seniority", "pass", True, seniority,
                            f"targets {sorted(facts.target_seniority)}")
    return CheckOutcome(
        "seniority", "fail", True, seniority,
        f"targets {sorted(facts.target_seniority)}",
        f"role is {seniority}, above the candidate's current level")


def _check_experience(jd: ParsedJD, facts: CandidateFacts) -> CheckOutcome | None:
    """Does the candidate meet a stated years-of-experience requirement?

    Only fires on a concrete number in the JD. A small overshoot is tolerated
    (requirements are usually aspirational), but a requirement far above what
    he has — the 10+ years on that sales-manager role — is a hard fail.
    """
    required = jd.years_experience
    if required is None or facts.years_experience is None:
        return None
    have = facts.years_experience
    ev = next((r.evidence for r in jd.requirements
               if r.field == "years_experience"), f"{required:g} years")
    if have + 1.0 >= required:
        return CheckOutcome("experience", "pass", False, ev,
                            f"has ~{have:g} years")
    if required >= have + 4.0:
        return CheckOutcome(
            "experience", "fail", True, ev, f"has ~{have:g} years",
            f"requires {required:g} years")
    # Between one and four years short: reachable but a stretch.
    return CheckOutcome(
        "experience", "unknown", True, ev, f"has ~{have:g} years",
        f"requires {required:g} years — a stretch, worth a human check")


def evaluate(
    jd: ParsedJD,
    facts: CandidateFacts,
    location: str | None = None,
    seniority: str | None = None,
) -> EligibilityReport:
    """Deterministic aggregation. See docs/ELIGIBILITY_ENGINE.md."""
    checks = [
        c
        for c in (
            _check_sponsorship(jd, facts),
            _check_degree(jd, facts),
            _check_employment_type(jd, facts),
            _check_location(location, facts),
            _check_seniority(seniority, facts),
            _check_experience(jd, facts),
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
