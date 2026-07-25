"""Tests for the Recommended/Backup role selection (2026-07-24 redesign).

Core rule under test: a UNIFORM score threshold across every company —
company standing already spends 38% of Application Priority's weight, so a
per-tier threshold would apply that signal twice. Tier only controls how
many roles a company must clear before backfill kicks in.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.company.portfolio import (
    BACKUP_FLOOR,
    RECOMMENDED_THRESHOLD,
    STRONG_RECOMMENDED_THRESHOLD,
    CompanyEntry,
    RoleEntry,
    select_company_roles,
)


def role(job_id, title, priority, *, band="R1", elig="PASS",
         deadline=None, applied=False) -> RoleEntry:
    return RoleEntry(
        job_id=job_id, title=title, role_type="software_engineering",
        role_band=band, application_priority=priority, eligibility=elig,
        already_applied=applied, application_deadline=deadline,
    )


def company(name, tier, roles, *, provisional=False) -> CompanyEntry:
    return CompanyEntry(
        company_id=name.lower(), name=name, tier=tier,
        tier_display=f"{tier}?" if provisional else tier,
        provisional=provisional, platform_value=90.0,
        evidence_coverage=0.85, roles=roles,
    )


def test_uniform_threshold_not_per_tier():
    """The exact case the redesign exists to prevent: a 71-point S-tier
    role must NOT read 'Backup' while a 63-point A-tier role reads
    'Recommended' — one global bar, no per-tier adjustment."""
    s_co = company("Cohere", "S", [role("s1", "SWE Intern", 71.0)])
    a_co = company("SomeCo", "A", [role("a1", "SWE Intern", 63.0)])
    s_sel = select_company_roles(s_co)
    a_sel = select_company_roles(a_co)
    assert s_sel.recommended and s_sel.recommended[0].job_id == "s1"
    assert not a_sel.recommended
    assert a_sel.backup and a_sel.backup[0].job_id == "a1"


def test_strong_flag_is_a_subset_of_recommended():
    co = company("X", "A", [
        role("hi", "Strong Role", STRONG_RECOMMENDED_THRESHOLD + 1),
        role("lo", "Just Recommended", RECOMMENDED_THRESHOLD + 1),
    ])
    sel = select_company_roles(co)
    assert {r.job_id for r in sel.recommended} == {"hi", "lo"}
    assert sel.strong_job_ids == {"hi"}


def test_r4_never_recommended_or_backfilled():
    co = company("X", "A", [role("r4", "Sales Rep", 99.0, band="R4")])
    sel = select_company_roles(co)
    assert sel.recommended == []
    assert sel.backup == []
    assert sel.shortfall_message is not None


def test_expired_deadline_excluded():
    past = datetime.now(UTC) - timedelta(days=1)
    co = company("X", "A", [role("old", "SWE Intern", 90.0, deadline=past)])
    sel = select_company_roles(co)
    assert sel.recommended == []
    assert sel.backup == []


def test_min_display_count_backfills_from_remaining_by_score():
    """A-tier needs 3. Two above threshold, two below — backfill takes the
    higher-scoring one of the two, in score order, not arbitrarily."""
    co = company("X", "A", [
        role("r1", "Role One", 76.0),
        role("r2", "Role Two", 68.0),
        role("r3", "Role Three", 60.0),   # below RECOMMENDED_THRESHOLD (64)
        role("r4", "Role Four", 55.0),    # below r3, still above BACKUP_FLOOR
    ])
    sel = select_company_roles(co)
    assert {r.job_id for r in sel.recommended} == {"r1", "r2"}
    assert [r.job_id for r in sel.backup] == ["r3"]
    assert sel.shortfall_message is None  # 2 + 1 = 3, meets the A-tier minimum


def test_backfill_never_dips_below_the_absolute_floor():
    co = company("X", "C", [role("weak", "Role", BACKUP_FLOOR - 1)])
    sel = select_company_roles(co)
    assert sel.recommended == []
    assert sel.backup == []
    assert sel.shortfall_message == "Only 0 eligible roles found."


def test_shortfall_message_reports_the_true_count_without_forcing_a_fill():
    co = company("X", "B", [role("only", "Role", 66.0)])  # B needs 2
    sel = select_company_roles(co)
    assert len(sel.recommended) == 1
    assert sel.backup == []
    assert sel.shortfall_message == "Only 1 eligible role found."


def test_backfill_deduplicates_by_normalized_title():
    """Same role cross-posted per city collapses to one backfill slot."""
    co = company("X", "B", [
        role("a", "Data Analyst Intern - Toronto", 60.0),
        role("b", "Data Analyst Intern (Vancouver)", 58.0),
        role("c", "Backend Engineer Intern", 52.0),
    ])
    sel = select_company_roles(co)
    # Only one of the two near-duplicate Data Analyst postings backfills,
    # so the distinct Backend Engineer role gets the second slot instead.
    backfilled_ids = {r.job_id for r in sel.backup}
    assert "c" in backfilled_ids
    assert not {"a", "b"} <= backfilled_ids


def test_already_applied_and_failed_roles_never_appear():
    co = company("X", "A", [
        role("done", "Applied Already", 90.0, applied=True),
        role("bad", "Ineligible", 90.0, elig="FAIL"),
    ])
    sel = select_company_roles(co)
    assert sel.recommended == []
    assert sel.backup == []
