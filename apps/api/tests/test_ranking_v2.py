"""Acceptance tests for the v2 ranking redesign (docs/INTERNSHIP_RANKING.md §26)."""

from __future__ import annotations

from app.company.intelligence import (
    CompanyDimension,
    Evidence,
    SourceGrade,
    assess_company,
    coverage_status,
)
from app.eligibility.engine import CandidateFacts, evaluate
from app.parsing.jd_parser import parse_jd
from app.ranking.gate import Gate, evaluate_gate
from app.ranking.modes import RankingMode, RankingProfile
from app.ranking.priority import compute_priority
from app.roles.taxonomy import RoleBand, classify_role
from app.skills.ontology import (
    CandidateSkillEvidence,
    EvidenceStrength,
    JDSkill,
    compute_fit,
    extract_skills,
)

D = CompanyDimension
G = SourceGrade


def _ev(dim, val, grade=G.A, stype="official_site", summary="evidence"):
    return Evidence(url="https://x", source_type=stype, grade=grade,
                    supports_dimension=dim, summary=summary, value=val)


def _big_platform() -> list[Evidence]:
    """Well-evidenced global platform: many dimensions, A-grade, 2+ types."""
    return [
        _ev(D.BRAND_SIGNAL, 0.98, G.A, "official_site", "global brand"),
        _ev(D.BRAND_SIGNAL, 0.95, G.B, "news", "mainstream coverage"),
        _ev(D.TECHNICAL_DENSITY, 0.92, G.A, "eng_blog", "engineering blog"),
        _ev(D.INTERNSHIP_PROGRAM, 0.95, G.A, "careers_page", "formal intern program"),
        _ev(D.CAREER_OPTIONALITY, 0.95, G.A, "careers_page", "many orgs"),
        _ev(D.SYSTEM_SCALE, 0.97, G.A, "eng_blog", "planet-scale systems"),
        _ev(D.TALENT_NETWORK, 0.9, G.B, "linkedin", "large alumni network"),
        _ev(D.STABILITY, 0.95, G.A, "annual_report", "profitable"),
    ]


def _unknown_startup() -> list[Evidence]:
    """Thin evidence: only a couple of dimensions known."""
    return [
        _ev(D.TECHNICAL_DENSITY, 0.9, G.A, "eng_blog", "strong AI papers"),
        _ev(D.BRAND_SIGNAL, 0.3, G.B, "news", "little coverage"),
    ]


def _domain_elite() -> list[Evidence]:
    """Small company, elite in its technical domain, real local presence."""
    return [
        _ev(D.TECHNICAL_DENSITY, 0.97, G.A, "research_page", "top AV research"),
        _ev(D.BRAND_SIGNAL, 0.55, G.B, "news", "known in industry only"),
        _ev(D.CAREER_OPTIONALITY, 0.7, G.A, "careers_page", "multiple tech teams"),
        _ev(D.INTERNSHIP_PROGRAM, 0.75, G.A, "careers_page", "intern program"),
        _ev(D.SYSTEM_SCALE, 0.8, G.A, "eng_blog", "real AV stack"),
        _ev(D.STABILITY, 0.7, G.B, "news", "well funded"),
        _ev(D.TALENT_NETWORK, 0.6, G.B, "linkedin", "strong local network"),
    ]


# ==================================================================== company

def test_high_brand_low_domain_does_not_get_s_everywhere():
    """A famous brand must not auto-win the technical-domain dimension."""
    ev = [
        _ev(D.BRAND_SIGNAL, 0.99, G.A, "official_site", "household name"),
        _ev(D.TECHNICAL_DENSITY, 0.25, G.A, "eng_blog", "little engineering"),
        _ev(D.INTERNSHIP_PROGRAM, 0.5, G.A, "careers_page", "small program"),
        _ev(D.CAREER_OPTIONALITY, 0.4, G.B, "linkedin", "narrow"),
        _ev(D.SYSTEM_SCALE, 0.3, G.B, "news", "modest systems"),
        _ev(D.STABILITY, 0.8, G.A, "annual_report", "stable"),
        _ev(D.TALENT_NETWORK, 0.4, G.B, "linkedin", "modest"),
    ]
    r = assess_company(ev)
    tech = next(d for d in r.dimensions if d.dimension is D.TECHNICAL_DENSITY)
    assert tech.score is not None and tech.score < 0.4
    assert r.estimated_tier != "S"


def test_domain_elite_not_treated_as_ordinary_small_company():
    r = assess_company(_domain_elite())
    tech = next(d for d in r.dimensions if d.dimension is D.TECHNICAL_DENSITY)
    assert tech.score is not None and tech.score >= 0.9   # elite in its domain
    assert r.estimated_tier in ("A", "B")                     # not dumped to C/D
    assert r.evidence_coverage >= 0.65


def test_insufficient_coverage_gives_only_provisional_status():
    r = assess_company(_unknown_startup())
    assert r.evidence_coverage < 0.65
    assert r.provisional is True
    assert r.rated_tier is None          # no formal rating while provisional
    assert r.display_tier.endswith("?") or "unrated" in r.display_tier


def test_tier_letter_and_coverage_are_independent_axes():
    """High evidence score + thin coverage => 'S?' + Provisional, NOT 'B?'.

    Coverage qualifies confidence; it must never rewrite the letter.
    """
    strong_but_thin = [
        _ev(D.BRAND_SIGNAL, 0.97, G.A, "official_site", "very strong brand"),
        _ev(D.TECHNICAL_DENSITY, 0.95, G.A, "eng_blog", "deep engineering"),
    ]
    r = assess_company(strong_but_thin)
    assert r.known_evidence_score > 88          # score axis says S
    assert r.estimated_tier == "S"
    assert r.rating_status == "provisional"     # coverage axis says provisional
    assert r.display_tier == "S?"               # NOT "B?"
    assert r.rated_tier is None


def test_grade_c_evidence_alone_cannot_change_tier_but_feeds_risk():
    """Anonymous reviews never move the score, but they are not discarded."""
    base = assess_company(_domain_elite())
    with_c = assess_company(
        _domain_elite()
        + [_ev(D.BRAND_SIGNAL, 0.99, G.C, "reddit", "anonymous hype")]
        + [_ev(D.STABILITY, 0.01, G.C, "blind", "anonymous doom")]
    )
    assert with_c.estimated_tier == base.estimated_tier
    assert with_c.known_evidence_score == base.known_evidence_score
    # ...but the negative anonymous signal registers on the independent radar.
    assert with_c.risk is not None
    assert with_c.risk.level.value != "none"
    assert with_c.risk.evidence_quality in ("low", "medium")


def test_many_consistent_c_signals_trigger_manual_research_not_demotion():
    ev = _domain_elite() + [
        _ev(D.STABILITY, 0.05, G.C, "blind", "layoff rumours"),
        _ev(D.STABILITY, 0.1, G.C, "reddit", "hiring freeze reports"),
        _ev(D.STABILITY, 0.05, G.C, "glassdoor", "poor outlook reviews"),
    ]
    r = assess_company(ev)
    assert r.risk is not None
    assert r.risk.manual_research_required is True
    # Tier is unchanged: anonymous signal is a radar, not a vote.
    assert r.estimated_tier == assess_company(_domain_elite()).estimated_tier


def test_s_tier_requires_grade_a_and_two_types_and_coverage():
    """Well-evidenced platform reaches S; the same scores with only B-grade do not."""
    assert assess_company(_big_platform()).rated_tier == "S"
    weak = [
        Evidence(url="u", source_type="news", grade=G.B, supports_dimension=e.supports_dimension,
                 summary="s", value=e.value)
        for e in _big_platform()
    ]
    assert assess_company(weak).rated_tier != "S"


def test_coverage_bands():
    assert coverage_status(0.2) == "unrated"
    assert coverage_status(0.5) == "provisional"
    assert coverage_status(0.7) == "medium"
    assert coverage_status(0.9) == "high"


# ============================================================ role & skills

def test_sales_engineer_is_not_software_engineering():
    r = classify_role("Sales Engineer", "Own quota, cold call prospects, upsell clients.")
    assert r.role_type != "software_engineering"
    assert r.band in (RoleBand.R3, RoleBand.R4)


def test_solutions_and_support_engineer_not_r1():
    for title in ("Solutions Engineer", "Support Engineer", "Field Engineer"):
        r = classify_role(title, "Help customers with the product.")
        assert r.band is not RoleBand.R1, f"{title} must not be R1"


def test_real_swe_is_r1():
    r = classify_role(
        "Software Development Engineer Intern",
        "Write code, design systems, deploy to production, own a module, APIs, Python.",
    )
    assert r.band is RoleBand.R1
    assert r.role_type == "software_engineering"
    assert r.technical_density > 0.4


def test_postgresql_does_not_substring_match_sql():
    """The old bug: 'sql' in 'postgresql'. Extraction must be word-boundary."""
    found = extract_skills("Experience with PostgreSQL required.")
    assert "postgresql" in found
    assert "sql" not in found          # NOT via spelling


def test_postgresql_implies_sql_explicitly():
    """SQL credit comes from an explicit ontology edge, at reduced strength."""
    fit = compute_fit(
        [JDSkill("sql", required=True)],
        [CandidateSkillEvidence("postgresql", EvidenceStrength.INTERNSHIP)],
    )
    detail = fit.details[0]
    assert detail.matched is True
    assert detail.via.startswith("implied:")
    assert detail.strength_factor < EvidenceStrength.INTERNSHIP.factor


def test_fit_reports_coverage_not_bare_precision():
    fit = compute_fit(
        [JDSkill("python", True), JDSkill("kubernetes", True)],
        [CandidateSkillEvidence("python", EvidenceStrength.PRODUCTION)],
    )
    assert fit.missing_required == ["kubernetes"]
    assert 0 < fit.conservative_score <= fit.known_evidence_score or fit.coverage < 1


# ================================================================== ranking

def _score(company_ev, title, body, cand_skills, jd_skills, facts=None,
           freshness=0.9, effort=20, deadline=None, source_status="open"):
    jd = parse_jd(body)
    facts = facts or CandidateFacts(highest_degree="bachelors", degree_rank=2,
                                    needs_sponsorship=False)
    gate = evaluate_gate(evaluate(jd, facts))
    return compute_priority(
        gate=gate,
        company=assess_company(company_ev),
        role=classify_role(title, body),
        fit=compute_fit(jd_skills, cand_skills),
        description=body,
        profile=RankingProfile.for_mode(RankingMode.INTERNSHIP),
        freshness=freshness,
        effort_minutes=effort,
        application_deadline=deadline,
        source_status=source_status,
    )


CAND = [
    CandidateSkillEvidence("python", EvidenceStrength.INTERNSHIP),
    CandidateSkillEvidence("postgresql", EvidenceStrength.PERSONAL_PROJECT),
]

SWE_BODY = ("Write code and design systems. Deploy to production, own a module, "
            "build APIs. Python. Bachelor's degree required.")
AI_BODY = ("Build ML models in PyTorch, deploy to production, own the pipeline. "
           "Python. Bachelor's degree required.")


def test_amazon_sde_beats_unknown_startup_ai():
    """Core preference: S-tier platform outranks a perfect-fit unknown startup."""
    big = _score(_big_platform(), "Software Development Engineer Intern",
                 SWE_BODY, CAND, [JDSkill("python", True)])
    small = _score(_unknown_startup(), "Applied AI Engineer Intern", AI_BODY,
                   CAND, [JDSkill("python", True)])
    assert big.application_priority > small.application_priority
    assert big.company_tier == "S"
    assert small.company_tier != "S"


def test_reduced_company_weight_lets_role_quality_compete():
    """2026-07-24: company weight dropped 50% -> 38% specifically so a strong
    role/team fit at an ordinary company could compete with platform alone —
    an S-tier R3 no longer automatically beats a well-evidenced R1 at an
    unrated startup, which is the point of the reweight, not a regression."""
    s_bi = _score(_big_platform(), "Business Intelligence Analyst Intern",
                  "Build dashboards, SQL queries, work with data teams, production reports.",
                  CAND, [JDSkill("sql", True)])
    c_backend = _score(_unknown_startup(), "Backend Engineer Intern",
                       SWE_BODY, CAND, [JDSkill("python", True)])
    assert s_bi.role_band == "R3"
    assert c_backend.role_band == "R1"
    # Company platform still dominates its own dimension...
    assert s_bi.company_platform_value.conservative > c_backend.company_platform_value.conservative
    # ...but no longer guarantees the overall win the way a 50% weight did.
    assert abs(s_bi.application_priority - c_backend.application_priority) < 5.0


def test_s_tier_sales_does_not_beat_b_tier_backend():
    """Platform is king, but the role must clear a floor. R4 is damped."""
    s_sales = _score(_big_platform(), "Sales Representative",
                     "Own quota, cold call prospects, upsell clients, commission.",
                     CAND, [JDSkill("python", True)])
    backend = _score(_domain_elite(), "Backend Engineer Intern", SWE_BODY,
                     CAND, [JDSkill("python", True)])
    assert s_sales.role_band == "R4"
    assert s_sales.application_priority < backend.application_priority
    assert s_sales.transferability <= 0.2


def test_freshness_only_reorders_and_cannot_rescue_a_bad_job():
    fresh_bad = _score(_big_platform(), "Sales Representative",
                       "Own quota, cold call prospects, commission.",
                       CAND, [JDSkill("python", True)], freshness=1.0)
    stale_good = _score(_big_platform(), "Software Development Engineer Intern",
                        SWE_BODY, CAND, [JDSkill("python", True)], freshness=0.05)
    assert stale_good.application_priority > fresh_bad.application_priority


def test_application_effort_never_changes_priority():
    """2026-07-24: effort is day-planning only, never a score input.

    An easy 1-click application is not a BETTER job than one requiring an
    essay — it is just quicker to knock out. The same posting scored with
    effort=2 and effort=60 must produce an identical application_priority.
    """
    easy = _score(_big_platform(), "Software Development Engineer Intern",
                  SWE_BODY, CAND, [JDSkill("python", True)], effort=2)
    hard = _score(_big_platform(), "Software Development Engineer Intern",
                  SWE_BODY, CAND, [JDSkill("python", True)], effort=60)
    assert easy.application_priority == hard.application_priority
    assert easy.application_effort_minutes == 2
    assert hard.application_effort_minutes == 60


def test_eligibility_fail_overrides_every_bonus():
    """An S-tier R1 role the user cannot legally take must not rank high."""
    body = SWE_BODY + " We are unable to provide visa sponsorship for this role."
    r = _score(_big_platform(), "Software Development Engineer Intern", body, CAND,
               [JDSkill("python", True)],
               facts=CandidateFacts(highest_degree="bachelors", degree_rank=2,
                                    needs_sponsorship=True))
    assert r.eligibility.gate is Gate.FAIL
    assert r.application_priority <= 5.0
    assert "ineligible" in r.recommendation.lower()


def test_eligibility_review_goes_to_manual_review():
    body = SWE_BODY + " We are unable to offer sponsorship."
    r = _score(_big_platform(), "Software Development Engineer Intern", body, CAND,
               [JDSkill("python", True)],
               facts=CandidateFacts(highest_degree="bachelors", degree_rank=2,
                                    needs_sponsorship=None))  # unknown
    assert r.eligibility.gate is Gate.REVIEW
    assert r.recommendation == "Manual Review"


def test_no_fake_precision_when_coverage_is_low():
    r = _score(_unknown_startup(), "Applied AI Engineer Intern", AI_BODY, CAND,
               [JDSkill("python", True)])
    assert r.company_platform_value.coverage < 0.65
    # The letter is qualified, never silently rewritten by coverage.
    assert "?" in r.company_tier_display
    assert "needs research" in " ".join(r.unknowns).lower()


def test_how_soon_only_changes_urgency_not_priority():
    """2026-07-24: 'closes in 2 days' must not make a job score higher than
    'closes in 60 days' — how soon only changes when to act.

    Whether a deadline is known AT ALL is a legitimate, separate viability
    signal ("is this a well-defined, structured posting" — per spec, part of
    Opportunity Viability, not urgency), so no-deadline vs has-a-deadline
    may legitimately score differently. But among postings that DO have a
    known deadline, how many days away it is must never move the score —
    only urgent/soon/normal/low, i.e. action_urgency.
    """
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    urgent = _score(_big_platform(), "Software Development Engineer Intern",
                    SWE_BODY, CAND, [JDSkill("python", True)],
                    deadline=now + timedelta(days=2))
    far_out = _score(_big_platform(), "Software Development Engineer Intern",
                     SWE_BODY, CAND, [JDSkill("python", True)],
                     deadline=now + timedelta(days=60))

    assert urgent.action_urgency == "urgent"
    assert far_out.action_urgency == "low"
    # Both have a KNOWN deadline — only how-soon differs, so score is identical.
    assert urgent.application_priority == far_out.application_priority


def test_deadline_known_is_a_viability_signal_not_urgency():
    """Whether a deadline is known at all IS allowed to move
    opportunity_viability (per spec: 'is the deadline known' is one of its
    inputs) — this is a distinct, legitimate signal from how-soon, which is
    action_urgency's job alone."""
    from datetime import UTC, datetime, timedelta

    no_deadline = _score(_big_platform(), "Software Development Engineer Intern",
                         SWE_BODY, CAND, [JDSkill("python", True)], deadline=None)
    has_deadline = _score(_big_platform(), "Software Development Engineer Intern",
                          SWE_BODY, CAND, [JDSkill("python", True)],
                          deadline=datetime.now(UTC) + timedelta(days=30))
    assert no_deadline.action_urgency == "unknown"
    assert has_deadline.action_urgency == "low"
    assert (has_deadline.opportunity_viability.conservative
            >= no_deadline.opportunity_viability.conservative)


def test_priority_is_not_presented_as_a_match_percentage():
    r = _score(_big_platform(), "Software Development Engineer Intern", SWE_BODY,
               CAND, [JDSkill("python", True)])
    d = r.as_dict()
    assert "application_priority" in d
    assert 0 <= d["application_priority"] <= 100
    assert "match_score" not in d and "match" not in d
    # The six scores are reported independently.
    for key in ("company_platform_value", "role_strategic_value",
                "current_candidate_fit", "team_project_quality",
                "career_optionality", "opportunity_viability", "evidence_coverage"):
        assert key in d


def test_internship_mode_weights_platform_above_fit():
    p = RankingProfile.for_mode(RankingMode.INTERNSHIP)
    assert p.weights.company_platform_value == 0.38
    assert p.weights.current_candidate_fit == 0.11
    assert p.weights.company_platform_value > p.weights.current_candidate_fit
    assert abs(p.weights.total() - 1.0) < 1e-9
    # Other modes must not inherit the 38%.
    assert RankingProfile.for_mode(RankingMode.NEW_GRAD).weights.company_platform_value < 0.38
    assert RankingProfile.for_mode(RankingMode.EXPERIENCED).weights.company_platform_value < 0.25


# ======================================== priority decomposition & clamping

def test_priority_is_clamped_and_is_a_plain_weighted_sum():
    """2026-07-24: no tier bonus, no priority floor — a plain weighted sum
    of the six dimensions (weights already sum to 1.0, so no normalization
    dance is needed either)."""
    r = _score(_big_platform(), "Software Development Engineer Intern", SWE_BODY,
               CAND, [JDSkill("python", True)])
    assert 0.0 <= r.application_priority <= 100.0
    assert abs(sum(r.contributions.values()) - r.application_priority) < 0.2


def test_contributions_explain_the_total():
    r = _score(_big_platform(), "Software Development Engineer Intern", SWE_BODY,
               CAND, [JDSkill("python", True)])
    assert "company_platform_value" in r.contributions
    assert abs(sum(r.contributions.values()) - r.application_priority) < 0.5
    # Company should visibly dominate in internship mode.
    assert r.contributions["company_platform_value"] > r.contributions["current_candidate_fit"]


# ============================== 2026-07-24 redesign regression tests

def test_career_optionality_enters_the_final_score():
    """The known bug this redesign fixes: career_optionality was computed
    but never added to application_priority. Two jobs identical except for
    role band (which drives optionality's breadth/transferability terms)
    must now produce different totals BECAUSE of the optionality gap, not
    despite it."""
    r1 = _score(_big_platform(), "Software Development Engineer Intern", SWE_BODY,
               CAND, [JDSkill("python", True)])
    r4 = _score(_big_platform(), "Sales Representative",
               "Own quota, cold call prospects, upsell clients, commission.",
               CAND, [JDSkill("python", True)])
    assert r1.career_optionality.conservative > r4.career_optionality.conservative
    assert r1.contributions["career_optionality"] > 0
    assert r1.contributions["career_optionality"] != r4.contributions["career_optionality"]


def test_company_platform_is_not_double_counted_via_optionality():
    """The other half of the same bug: optionality used to be 60% company
    score, which (on top of company already being its own weighted
    dimension) hid another ~5.4 points of company weight inside a
    dimension that was supposed to be about the CANDIDATE's next steps.
    Company standing may now only nudge optionality through the capped
    10%-of-10% internal-mobility term — at most ~1 point of the total
    application_priority, not the ~5+ points the old formula hid."""
    same_role_s = _score(_big_platform(), "Software Development Engineer Intern",
                         SWE_BODY, CAND, [JDSkill("python", True)])
    same_role_d = _score(
        [Evidence(url="u", source_type="news", grade=G.C, supports_dimension=D.BRAND_SIGNAL,
                  summary="s", value=0.1)],
        "Software Development Engineer Intern", SWE_BODY, CAND, [JDSkill("python", True)],
    )
    optionality_gap = (same_role_s.career_optionality.conservative
                       - same_role_d.career_optionality.conservative)
    # Same role/band => transferability, breadth and story-potential terms
    # are identical; only the 10%-weighted mobility term can differ, capped
    # at (1.0 - 0.2) * 0.10 = 8 points of optionality's OWN 0-100 scale.
    assert optionality_gap <= 8.5


def test_ownership_language_only_moves_team_quality_not_role_direction():
    """Ownership/production evidence used to live in both role_strategic_value
    and team_project_quality. Now the same JD body, swapped between
    ownership-heavy and support-only phrasing, must move team_project_quality
    while leaving role_strategic_value's direction/scope terms untouched —
    those come from the role's TYPE and BAND, not from reading these words."""
    owned_body = ("Own the roadmap, design and build the core product, deploy to "
                  "production, ship end-to-end. Python required.")
    support_body = ("Assist the team with data entry and generate reports under "
                    "close supervision. Python required.")
    owned = _score(_big_platform(), "Software Development Engineer Intern",
                   owned_body, CAND, [JDSkill("python", True)])
    support = _score(_big_platform(), "Software Development Engineer Intern",
                     support_body, CAND, [JDSkill("python", True)])

    assert owned.team_project_quality.conservative > support.team_project_quality.conservative
    # Role family alignment and structural scope are driven by role type/band
    # (both postings classify the same way here), not by these words.
    assert owned.role_band == support.role_band


def test_missing_team_evidence_lowers_confidence_not_the_score_directly():
    """No JD body => team_project_quality must read as the neutral prior
    (50, low coverage), never a fabricated low or high score."""
    r = _score(_big_platform(), "Software Development Engineer Intern", "",
               CAND, [])
    assert r.team_project_quality.coverage == 0.0
    assert r.team_project_quality.conservative == 50.0
    assert r.team_project_quality.known_evidence is None


def test_role_classification_reports_three_layers():
    r = classify_role(
        "Data Analyst Intern",
        "Run experiments, build data models, heavy SQL and Python, schema design, "
        "A/B test analysis, deploy pipelines to production.",
    )
    assert r.title_prior_band is not None
    assert r.jd_content_band is not None
    assert r.jd_content_summary
    # Technical content promotes a nominally R3 title.
    assert r.adjustment == "promoted"
    assert r.band is RoleBand.R2
    assert r.evidence


def test_pure_sales_title_stays_demoted_despite_engineer_word():
    r = classify_role(
        "Solutions Engineer",
        "Own quota, cold call prospects, upsell clients, manage client relationship.",
    )
    assert r.title_prior_band is not None
    assert r.band in (RoleBand.R3, RoleBand.R4)
    assert r.transferability <= 0.8


# ================================ persistence column-width safety (Postgres)

def test_persisted_string_columns_fit_worst_case_values():
    """SQLite ignores VARCHAR length; Postgres enforces it.

    A value that overflows only shows up in production, so assert the widest
    realistic strings fit the declared column widths.
    """
    from app.models.ranking_v2 import ApplicationPriorityScore as APS

    cols = APS.__table__.columns
    worst = {
        # e.g. "C? (unrated)"
        "company_tier_display": max(
            len(t) for t in ("S", "S?", "C? (unrated)", "Unrated")
        ),
        "eligibility_gate": len("REVIEW"),
        "company_tier": len("S"),
        "role_band": len("R1"),
        "role_type": len("nontechnical_business_development"),
        "recommendation": len("Apply / Research Company"),
        "action_urgency": len("unknown"),
        # No more floor/bonus qualifiers (2026-07-24: no priority floor, no
        # tier bonus), but keep a margin for the longest plain rule string.
        "interaction_rule": len(
            "S+R3 -> Serious Apply (platform compensates)"
        ),
        "ranking_mode": len("experienced"),
        "formula_version": len("legacy-v1"),
        "weights_version": len("v3-internship-default"),
    }
    for name, needed in worst.items():
        declared = cols[name].type.length
        assert declared is not None and declared >= needed, (
            f"{name}: declared VARCHAR({declared}) < worst-case {needed} chars"
        )


def test_display_tier_strings_are_bounded():
    """Whatever assess_company can emit must fit the persisted column."""
    from app.models.ranking_v2 import ApplicationPriorityScore as APS

    limit = APS.__table__.columns["company_tier_display"].type.length
    for ev in ([], _unknown_startup(), _domain_elite(), _big_platform()):
        assert len(assess_company(ev).display_tier) <= limit
