"""The seniority and experience gates.

A "Senior Manager, Commercial Sales" requiring 10+ years reached a co-op
student's inbox marked eligible. The gate was reading the JD text for
sponsorship, degree and location, but nothing compared the role's level or its
experience requirement against the candidate — because the candidate profile
was fictional seed data with no target level and no years recorded.
"""

from __future__ import annotations

import pytest

from app.eligibility.engine import (
    CandidateFacts,
    Verdict,
    detect_seniority,
    evaluate,
)
from app.parsing.jd_parser import parse_jd
from app.ranking.gate import Gate, evaluate_gate


def _coop_student() -> CandidateFacts:
    return CandidateFacts(
        work_auth_countries={"CA"},
        target_employment_types={"internship", "co_op", "new_grad"},
        target_seniority={"intern", "co_op", "new_grad", "entry"},
        years_experience=1.0,
    )


def _gate(title: str, description: str = "", location: str = "Toronto, ON") -> Gate:
    jd = parse_jd(description)
    seniority = detect_seniority(title, jd.years_experience)
    return evaluate_gate(
        evaluate(jd, _coop_student(), location=location, seniority=seniority)
    ).gate


# --------------------------------------------------------------------------
# Seniority detection from titles
# --------------------------------------------------------------------------
@pytest.mark.parametrize("title,expected", [
    ("Senior Manager, Commercial Sales", "manager"),
    ("Software Engineer Intern (Fall 2026)", "intern"),
    ("Machine Learning Intern/Co-op", "intern"),
    ("New Grad Software Engineer", "new_grad"),
    ("Senior Software Engineer", "senior"),
    ("Staff Software Engineer", "principal"),
    ("Principal Product Manager", "principal"),
    ("Director of Customer Success", "director"),
    ("VP, Fraud Strategy", "vp"),
    ("Data Analyst, Business Intelligence", None),  # no level marker
    ("Junior Data Analyst", "junior"),
])
def test_seniority_detection(title: str, expected: str | None) -> None:
    assert detect_seniority(title) == expected


def test_intern_beats_senior_in_the_same_title() -> None:
    """'Senior Software Engineer Intern' is an internship, not a senior role."""
    assert detect_seniority("Senior Software Engineer Intern") == "intern"


def test_years_requirement_does_not_infer_seniority() -> None:
    """Title only. Years are owned by the experience check, which has a
    gradient, so a plain title stays unmarked regardless of years stated."""
    assert detect_seniority("Analyst", years_required=10) is None
    assert detect_seniority("Analyst", years_required=1) is None


# --------------------------------------------------------------------------
# The gate the user caught
# --------------------------------------------------------------------------
def test_senior_manager_ten_years_fails_for_a_coop_student() -> None:
    assert _gate(
        "Senior Manager, Commercial Sales",
        "Undergraduate/Graduate degree and/or 10+ years of relevant experience",
        "Hamilton, Ontario",
    ) is Gate.FAIL


@pytest.mark.parametrize("title", [
    "Senior Software Engineer", "Staff Data Scientist",
    "Principal Product Manager", "Director of Engineering", "VP, Data",
])
def test_all_senior_and_above_roles_fail(title: str) -> None:
    assert _gate(title) is Gate.FAIL


@pytest.mark.parametrize("title", [
    "Software Engineer Intern", "Data Analyst Co-op",
    "Machine Learning Intern", "New Grad Software Engineer",
])
def test_early_career_roles_pass(title: str) -> None:
    assert _gate(title) is Gate.PASS


def test_plain_title_is_not_rejected_on_seniority_alone() -> None:
    """An unmarked 'Data Analyst' must not be guessed junior or senior."""
    assert _gate("Data Analyst, Business Intelligence") is Gate.PASS


@pytest.mark.parametrize("title,expected", [
    # "Manager" in a product/project title is a role noun, not a level.
    ("Associate Product Manager", "junior"),
    ("Product Manager", None),
    ("Senior Product Manager", "senior"),
    ("Technical Product Manager", None),
    ("Product Owner", None),
    ("Engineering Manager", "manager"),
    ("Manager, Software Development", "manager"),
    # A senior prefix must beat the junior-sounding "Associate".
    ("Associate Director, HRBP", "director"),
    ("Associate Principal Architect", "principal"),
    ("Associate Software Engineer", "junior"),
    # Numeric levels: III and up are past entry.
    ("Data Engineer III", "senior"),
    ("Software Engineer II", None),
    # French management titles.
    ("Gestionnaire, Stratégie", "manager"),
])
def test_seniority_edge_cases(title: str, expected: str | None) -> None:
    assert detect_seniority(title) == expected


def test_apm_a_named_target_is_not_screened_as_a_manager() -> None:
    """Associate Product Manager is entry-level product — one of his targets."""
    assert _gate("Associate Product Manager") is Gate.PASS


# --------------------------------------------------------------------------
# Role-family fit: non-technical roles are off-target for a technical candidate
# --------------------------------------------------------------------------
def _tech_student() -> CandidateFacts:
    facts = _coop_student()
    facts.technical_candidate = True
    return facts


def _fit_gate(title: str, description: str = "") -> Gate:
    from app.roles.taxonomy import classify_role

    jd = parse_jd(description)
    role = classify_role(title, description)
    return evaluate_gate(evaluate(
        jd, _tech_student(), location="Toronto, ON",
        seniority=detect_seniority(title, jd.years_experience),
        role_band=role.band.value, role_type=role.role_type,
    )).gate


@pytest.mark.parametrize("title", [
    "Account Executive", "Customer Support Specialist",
    "Client Success Coordinator", "Events Specialist, Tradeshows",
    "Content Writer", "Communications Manager",
    "Associate Director, HRBP", "Recruiter", "Executive Assistant",
])
def test_non_technical_roles_are_screened_out(title: str) -> None:
    assert _fit_gate(title) is Gate.FAIL


@pytest.mark.parametrize("title", [
    "Software Engineer Intern", "Data Analyst Co-op",
    "Machine Learning Intern", "Backend Developer, New Grad",
    "Associate Product Manager", "Data Engineer",
])
def test_technical_and_product_roles_pass_the_fit_gate(title: str) -> None:
    assert _fit_gate(title) is Gate.PASS


def test_role_fit_does_not_fire_without_a_technical_candidate() -> None:
    """The screen is opt-in; a non-technical candidate keeps sales roles."""
    from app.roles.taxonomy import classify_role

    role = classify_role("Account Executive", "")
    report = evaluate(parse_jd(""), _coop_student(), location="Toronto",
                      role_band=role.band.value, role_type=role.role_type)
    assert report.verdict is not Verdict.INELIGIBLE


# --------------------------------------------------------------------------
# Experience gate independent of title
# --------------------------------------------------------------------------
def test_ten_years_required_fails_even_without_a_senior_title() -> None:
    assert _gate(
        "Data Analyst", "Requires 10+ years of experience in analytics"
    ) is Gate.FAIL


def test_a_small_overshoot_is_tolerated() -> None:
    """Requirements are aspirational; 2 years vs his ~1 is not a hard bar."""
    assert _gate("Data Analyst", "2+ years of experience preferred") is Gate.PASS


def test_a_stretch_requirement_is_review_not_fail() -> None:
    jd = parse_jd("4+ years of experience required")
    report = evaluate(jd, _coop_student(), location="Toronto",
                      seniority=detect_seniority("Data Analyst", jd.years_experience))
    assert report.verdict in (Verdict.UNCERTAIN, Verdict.LIKELY_INELIGIBLE)


# --------------------------------------------------------------------------
# The gate only fires when the candidate's targets are known
# --------------------------------------------------------------------------
def test_without_a_target_level_seniority_is_not_gated() -> None:
    """An empty profile must not silently reject everything — the engine never
    guesses. This is why loading the real profile mattered."""
    blank = CandidateFacts(work_auth_countries={"CA"})
    jd = parse_jd("10+ years of experience")
    report = evaluate(jd, blank, location="Toronto",
                      seniority=detect_seniority("Senior Manager", 10))
    assert report.verdict is Verdict.ELIGIBLE
