"""Acceptance tests for the company-tier-centric inbox (spec section 16).

Core rule under test throughout:
    Tier organises COMPANIES. Application Priority orders ROLES.
"""

from __future__ import annotations

from app.applications.recommendation import (
    build_application_set,
    cluster_similar_roles,
    redundancy_risk,
    title_similarity,
)
from app.company.portfolio import (
    PROVISIONAL_BUCKET,
    CompanyEntry,
    RoleEntry,
    RoleFamily,
    companies_requiring_action,
    global_priority_queue,
    group_by_tier,
    role_family,
)


def role(job_id, title, priority, *, role_type="software_engineering", band="R1",
         elig="PASS", location="Toronto, ON", dept=None, applied=False,
         official=True, rsv=80.0, fit=80.0, student=True) -> RoleEntry:
    return RoleEntry(
        job_id=job_id, title=title, role_type=role_type, role_band=band,
        application_priority=priority, eligibility=elig, location=location,
        department=dept, already_applied=applied,
        canonical_url=f"https://boards.example/{job_id}" if official else None,
        discovery_url=None if official else "https://linkedin.example/x",
        role_strategic_value=rsv, current_fit=fit, is_student_role=student,
    )


def company(name, tier, roles, *, provisional=False, platform=90.0,
            coverage=0.85, cid=None) -> CompanyEntry:
    return CompanyEntry(
        company_id=cid or name.lower(), name=name, tier=tier,
        tier_display=f"{tier}?" if provisional else tier,
        provisional=provisional, platform_value=platform,
        evidence_coverage=coverage, roles=roles,
    )


# ============================================== 1-4  tier & company organisation

def test_1_companies_appear_in_their_tier():
    amazon = company("Amazon", "S", [role("a1", "SDE Intern", 93)])
    rbc = company("RBC", "A", [role("r1", "Data Engineering Analyst", 92)])
    groups = {g.tier: g for g in group_by_tier([amazon, rbc])}
    assert [c.name for c in groups["S"].companies] == ["Amazon"]
    assert [c.name for c in groups["A"].companies] == ["RBC"]


def test_2_provisional_company_never_shown_in_a_formal_tier():
    startup = company("Unknown AI Startup", "A", [role("u1", "AI Engineer Intern", 88)],
                      provisional=True, coverage=0.48)
    groups = {g.tier: g for g in group_by_tier([startup])}
    assert "A" not in groups
    assert PROVISIONAL_BUCKET in groups
    assert startup.bucket == PROVISIONAL_BUCKET
    assert startup.tier_display.endswith("?")


def test_3_company_moves_tier_once_evidence_is_sufficient():
    startup = company("Unknown AI Startup", "A", [role("u1", "AI Intern", 88)],
                      provisional=True, coverage=0.48)
    assert startup.bucket == PROVISIONAL_BUCKET
    # Research completes: coverage rises, the rating becomes formal.
    startup.provisional = False
    startup.evidence_coverage = 0.86
    startup.tier_display = "A"
    assert startup.bucket == "A"
    assert group_by_tier([startup])[0].tier == "A"


def test_4_card_counts_match_the_role_list():
    roles = [role("x1", "SDE Intern", 90), role("x2", "Data Intern", 85,
                                                role_type="data_engineering"),
             role("x3", "Closed One", 80, elig="FAIL"),
             role("x4", "Done", 70, applied=True)]
    c = company("Acme", "A", roles)
    assert len(c.relevant_roles) == 2          # FAIL and applied are excluded
    assert len(c.applied_roles) == 1
    assert len(c.top_roles()) == len(c.relevant_roles)
    group = group_by_tier([c])[0]
    assert group.role_count == len(c.relevant_roles)


# ================================================ 5-9  in-company ranking

def test_5_roles_inside_a_company_sort_by_application_priority():
    c = company("Acme", "S", [
        role("a", "Data Intern", 78, role_type="data_engineering"),
        role("b", "SDE Intern", 93),
        role("c", "Program Intern", 84, role_type="technical_program_management",
             band="R2"),
    ])
    assert [r.application_priority for r in c.ranked_roles()] == [93, 84, 78]


def test_6_near_identical_roles_do_not_all_enter_the_set():
    c = company("Amazon", "S", [
        role("s1", "Software Engineer Intern", 93, dept="Retail"),
        role("s2", "Software Developer Intern", 90, dept="Retail"),
        role("s3", "Backend Software Engineer Intern", 88, dept="Retail"),
    ])
    result = build_application_set(c)
    assert len(result.recommended) == 1, "three near-duplicates must collapse to one"
    assert result.recommended[0].role.job_id == "s1"      # the highest scoring
    assert any("similar" in e.reason for e in result.excluded)


def test_7_distinct_role_families_can_all_be_recommended():
    c = company("Amazon", "S", [
        role("s1", "Software Engineer Intern", 93),
        role("d1", "Data Engineer Intern", 91, role_type="data_engineering"),
        role("p1", "Technical Program Intern", 88,
             role_type="technical_program_management", band="R2"),
    ])
    result = build_application_set(c)
    assert len(result.recommended) == 3
    families = {r.role.family for r in result.recommended}
    assert families == {RoleFamily.SOFTWARE, RoleFamily.DATA_ENGINEERING,
                        RoleFamily.PROGRAM}


def test_8_already_applied_similar_role_suppresses_a_duplicate():
    c = company("Amazon", "S", [
        role("done", "Software Engineer Intern", 93, applied=True, dept="Retail"),
        role("dup", "Software Developer Intern", 90, dept="Retail"),
        role("new", "Data Engineer Intern", 85, role_type="data_engineering"),
    ])
    result = build_application_set(c)
    ids = [r.role.job_id for r in result.recommended]
    assert "dup" not in ids, "should not re-apply to a near-identical role"
    assert "new" in ids
    assert result.already_applied == 1


def test_9_s_tier_shows_more_roles_but_limit_still_applies():
    roles = [role(f"r{i}", f"Role {i}", 90 - i,
                  role_type=list(
                      ["software_engineering", "data_engineering", "applied_ai",
                       "technical_product", "cloud_engineering", "bi_analyst"])[i])
             for i in range(6)]
    s = company("BigCo", "S", roles)
    b = company("SmallCo", "B", list(roles))
    assert len(s.top_roles()) == 5      # display allowance for S
    assert len(b.top_roles()) == 3      # display allowance for B
    # Display count is not the application limit.
    assert len(build_application_set(s).recommended) <= 4
    assert len(build_application_set(b).recommended) <= 3


# ================================================== 10-13  cross-tier ranking

def test_10_a_tier_top_role_outranks_s_tier_mediocre_role():
    wealthsimple = company("Wealthsimple", "A",
                           [role("w1", "Product Data Intern", 94,
                                 role_type="data_platform_analyst", band="R2")])
    amazon = company("Amazon", "S", [role("a1", "BI Analyst Intern", 84,
                                          role_type="bi_analyst", band="R3")])
    queue = global_priority_queue([amazon, wealthsimple])
    assert queue[0][0].name == "Wealthsimple"
    assert queue[0][1].application_priority == 94


def test_11_tier_does_not_group_the_global_queue():
    s1 = company("S-Co", "S", [role("s1", "Role", 95), role("s2", "Role B", 60,
                                                            role_type="bi_analyst")])
    a1 = company("A-Co", "A", [role("a1", "Role", 80)])
    order = [r.application_priority for _, r in global_priority_queue([s1, a1])]
    assert order == [95, 80, 60], "must interleave across tiers, not group by tier"


def test_12_s_tier_r4_role_does_not_ride_the_platform_to_the_top():
    """An R4 role's low priority is produced upstream; the queue must respect it."""
    amazon = company("Amazon", "S", [role("sales", "Sales Representative", 45,
                                          role_type="sales", band="R4", student=False)])
    small = company("SmallCo", "B", [role("be", "Backend Intern", 82,
                                          role_type="backend_engineering")])
    queue = global_priority_queue([amazon, small])
    assert queue[0][0].name == "SmallCo"


def test_13_high_potential_unrated_company_surfaces_for_research():
    startup = company("Unknown AI Startup", "A",
                      [role("u1", "Applied AI Intern", 66, role_type="applied_ai",
                            rsv=92.0, fit=91.0)],
                      provisional=True, coverage=0.47)
    assert startup.high_potential_unrated is True
    actions = dict((c.name, reasons) for c, reasons in
                   companies_requiring_action([startup], min_priority=90))
    assert any("research" in r for r in actions["Unknown AI Startup"])


# ==================================================== 14-18  application count

def test_14_no_hardcoded_one_application_per_company():
    c = company("Amazon", "S", [
        role("s1", "Software Engineer Intern", 93),
        role("d1", "Data Engineer Intern", 90, role_type="data_engineering"),
    ])
    assert len(build_application_set(c).recommended) == 2


def test_15_highly_similar_roles_are_capped():
    c = company("Acme", "S", [
        role(f"s{i}", "Software Engineer Intern", 90 - i, dept="Core")
        for i in range(5)
    ])
    result = build_application_set(c)
    assert len(result.recommended) == 1


def test_16_different_teams_allow_multiple_applications():
    c = company("Acme", "S", [
        role("t1", "Software Engineer Intern", 90, dept="Payments"),
        role("t2", "Data Engineer Intern", 89, role_type="data_engineering",
             dept="Risk"),
    ])
    assert len(build_application_set(c).recommended) == 2


def test_17_exceeding_the_limit_explains_itself():
    c = company("Acme", "C", [           # C tier limit is 2
        role("a", "Software Engineer Intern", 90),
        role("b", "Data Engineer Intern", 89, role_type="data_engineering"),
        role("c", "Applied AI Intern", 88, role_type="applied_ai"),
        role("d", "Product Analyst Intern", 87, role_type="technical_product",
             band="R2"),
    ])
    result = build_application_set(c)
    assert len(result.recommended) == 2
    assert result.over_limit is True
    assert result.notes, "must state why extra roles were held back"
    assert any("limit" in e.reason for e in result.excluded)


def test_18_user_can_override_the_limit():
    c = company("Acme", "C", [
        role("a", "Software Engineer Intern", 90),
        role("b", "Data Engineer Intern", 89, role_type="data_engineering"),
        role("c", "Applied AI Intern", 88, role_type="applied_ai"),
    ])
    assert len(build_application_set(c).recommended) == 2
    assert len(build_application_set(c, limit=3).recommended) == 3


# ====================================================== 19-21  official sources

def test_19_official_roles_are_marked_and_third_party_flagged():
    official = role("o1", "SDE Intern", 90)
    third = role("t1", "Data Intern", 88, role_type="data_engineering",
                 official=False)
    assert official.is_official is True
    assert third.is_official is False
    c = company("Acme", "A", [official, third])
    result = build_application_set(c)
    flagged = [r for r in result.recommended if not r.role.is_official]
    assert flagged and "official link" in flagged[0].reason


def test_20_third_party_only_roles_are_surfaced_as_needing_action():
    c = company("Acme", "A", [role("t1", "Data Intern", 88, official=False)])
    reasons = dict((x.name, r) for x, r in companies_requiring_action([c]))
    assert any("official link" in r for r in reasons["Acme"])


def test_21_closed_role_drops_out_of_the_recommended_set():
    c = company("Acme", "A", [
        role("open", "Data Engineer Intern", 88, role_type="data_engineering"),
        role("closed", "SDE Intern", 95, elig="FAIL"),
    ])
    result = build_application_set(c)
    ids = [r.role.job_id for r in result.recommended]
    assert ids == ["open"], "an ineligible/closed role must not be recommended"


# ============================================================ helper behaviour

def test_role_family_mapping():
    assert role_family("backend_engineering") is RoleFamily.BACKEND
    assert role_family("bi_analyst") is RoleFamily.ANALYTICS
    assert role_family("sales") is RoleFamily.OTHER


def test_title_similarity_ignores_term_words():
    # "Intern" appears in nearly every student posting and must not create
    # false similarity between unrelated roles.
    assert title_similarity("Software Engineer Intern",
                            "Software Developer Intern") > 0.4
    assert title_similarity("Software Engineer Intern",
                            "Data Analyst Intern") < 0.5


def test_redundancy_risk_is_low_across_families():
    a = role("a", "Software Engineer Intern", 90)
    b = role("b", "Data Engineer Intern", 88, role_type="data_engineering")
    assert redundancy_risk(a, b) < 0.75


def test_clustering_assigns_group_ids():
    roles = [role("a", "Software Engineer Intern", 90, dept="X"),
             role("b", "Software Developer Intern", 88, dept="X"),
             role("c", "Applied AI Intern", 85, role_type="applied_ai")]
    groups = cluster_similar_roles(roles)
    assert len(groups) == 2
    assert all(r.similarity_group_id for r in roles)
