"""Guards on the company layer: gate, two-pass tiering, and capture honesty.

The calibration cases below are the ones that exposed real defects:
a tier that moved when a single requisition opened or closed; a Canada-only
company scored 0.2/1.0 on "brand"; a small named first-choice buried in C.
"""

from __future__ import annotations

import pytest

from app.company.access import (
    CanadaAccess,
    CaptureStatus,
    LocationClass,
    assess_access,
    classify_location,
)
from app.company.gate import GATED_OUT, Gate, evaluate
from app.company.profiles import (
    ALL_PROFILES,
    BY_KEY,
    EXCLUSIONS,
    PERSONAL_BANDS,
    TIER_BANDS,
    adjustments,
    resolve,
    tier_counts,
)

TIERS = {"S", "A", "B", "C", "D"}


# --------------------------------------------------------------------------
# Registry integrity
# --------------------------------------------------------------------------
def test_no_duplicate_company_entities() -> None:
    """One employer, one profile. An earlier table listed four companies twice."""
    keys = [p.key for p in ALL_PROFILES]
    assert len(keys) == len(set(keys))
    names = [p.name.lower() for p in ALL_PROFILES]
    assert len(names) == len(set(names))


def test_every_profile_is_well_formed() -> None:
    for p in ALL_PROFILES:
        assert p.platform_tier in TIERS, p.key
        assert p.personal_tier in TIERS, p.key
        assert len(p.why) > 40, p.key  # a tier nobody can audit is an opinion
        assert p.assessed_on < p.valid_until, p.key
        for field, value in (("brand_ca", p.brand_ca), ("brand_us", p.brand_us),
                             ("brand_cn", p.brand_cn), ("depth", p.depth),
                             ("role", p.role), ("domain", p.domain),
                             ("founder", p.founder), ("program", p.program),
                             ("tech", p.tech)):
            assert 0 <= value <= 3, (p.key, field, value)


def test_every_judgment_override_states_a_reason() -> None:
    """Pass 2 may move anything, but never silently."""
    for p in ALL_PROFILES:
        if p.override or p.override_personal:
            assert p.override_reason, p.key
            assert len(p.override_reason) > 30, p.key


def test_boards_map_back_to_exactly_one_entity() -> None:
    seen: dict[str, str] = {}
    for p in ALL_PROFILES:
        for conn, ext in p.boards:
            token = f"{conn}:{ext}".lower()
            assert token not in seen, (token, seen.get(token), p.key)
            seen[token] = p.key
            assert resolve(token) is p


@pytest.mark.parametrize("name,key", [
    ("OpenAI", "openai"), ("Thomson Reuters", "thomsonreuters"),
    ("Thomson", "thomsonreuters"), ("TD Bank", "td"),
    ("Ceridian", "dayforce"), ("Equitable Bank", "eqbank"),
])
def test_alias_resolution(name: str, key: str) -> None:
    got = resolve(name)
    assert got is not None and got.key == key


def test_tiers_are_usably_sized() -> None:
    """A tier holding a third of the registry conveys nothing."""
    total = len(ALL_PROFILES)
    for by in ("platform", "personal"):
        counts = tier_counts(by)
        assert sum(counts.values()) == total
        assert counts["S"] <= total * 0.10, (by, counts)
        for tier, n in counts.items():
            assert n <= total * 0.45, (by, tier, n)


# --------------------------------------------------------------------------
# The gate runs before tiering, so "impossible" never lands in D
# --------------------------------------------------------------------------
def test_gate_rejects_before_tiering_rather_than_ranking_low() -> None:
    result = evaluate(name="Some US startup", hires_in_canada=False)
    assert result.gate is Gate.NO_CANADIAN_HIRING
    assert result.tierable is False


def test_remote_open_to_canada_passes_the_gate() -> None:
    result = evaluate(name="Remote-first", hires_in_canada=False,
                      remote_open_to_canada=True)
    assert result.passed


def test_hard_to_get_is_not_a_gate() -> None:
    """Difficulty belongs to the ranking; only structural bars gate."""
    assert evaluate(name="Google", hires_in_canada=True).passed


def test_gated_out_categories_all_carry_reasons() -> None:
    assert GATED_OUT
    for label, result in GATED_OUT.items():
        assert result.gate is not Gate.PASS, label
        assert len(result.reason) > 20, label


def test_exclusions_are_documented() -> None:
    assert len(EXCLUSIONS) >= 8
    for label, reason in EXCLUSIONS.items():
        assert len(reason) > 30, label


# --------------------------------------------------------------------------
# Two-pass calibration
# --------------------------------------------------------------------------
def test_canada_only_company_is_not_structurally_penalised() -> None:
    """Wealthsimple scored 0.2/1.0 on brand under the old region-count proxy."""
    ws = BY_KEY["wealthsimple"]
    assert ws.personal_tier == "S"
    assert ws.brand > 0.6


def test_technical_reputation_only_ever_adds() -> None:
    """Canadian recognition plus a stable co-op programme is worth an A alone."""
    manulife = BY_KEY["manulife"]
    assert manulife.platform_tier == "A"
    assert manulife.tech <= 1  # it earns A without any engineering bonus
    # And the top of the platform band is unreachable without engineering.
    for key in ("amazon", "google", "microsoft"):
        assert BY_KEY[key].platform_tier == "S"
        assert BY_KEY[key].tech == 3


def test_named_first_choices_are_floored() -> None:
    """BioAdvance landed in C purely for being small; he named it Tier 1."""
    bio = BY_KEY["bioadvance"]
    assert bio.algo_personal_tier == "C"
    assert bio.personal_tier == "A"


def test_safety_nets_can_never_displace_a_real_target() -> None:
    for p in ALL_PROFILES:
        if p.safety_net:
            assert p.personal_tier in ("B", "C", "D"), p.key
    assert any(p.safety_net for p in ALL_PROFILES)


def test_public_sector_is_present_but_only_as_a_floor() -> None:
    for key in ("cityoftoronto", "ops", "metrolinx"):
        assert BY_KEY[key].safety_net is True


def test_bank_of_canada_is_not_treated_as_a_floor_option() -> None:
    """Real research work, unlike the rest of the public sector."""
    assert BY_KEY["bankofcanada"].safety_net is False


def test_brand_does_not_lift_a_non_technical_seat() -> None:
    for key in ("td", "manulife", "capitalone", "cityoftoronto", "visa"):
        assert BY_KEY[key].role_floor is True


def test_health_data_institutes_rank_on_domain_not_fame() -> None:
    """ICES has almost no public brand and is one of his best domain matches."""
    ices = BY_KEY["ices"]
    assert ices.domain == 3
    assert ices.personal_tier in ("A", "B")


def test_adjustments_are_enumerable() -> None:
    for p in adjustments():
        assert p.platform_tier != p.algo_tier or p.personal_tier != p.algo_personal_tier


def test_band_definitions_are_ordered_and_distinct() -> None:
    for bands in (TIER_BANDS, PERSONAL_BANDS):
        floors = [f for f, _ in bands]
        assert floors == sorted(floors, reverse=True)
        assert len({t for _, t in bands}) == 5


# --------------------------------------------------------------------------
# Canada access is a status, never a tier modifier
# --------------------------------------------------------------------------
def test_no_canadian_opening_does_not_lower_platform_tier() -> None:
    """The single most serious defect in the previous ranking."""
    for key in ("openai", "anthropic"):
        assert BY_KEY[key].platform_tier == "S"
    access = assess_access([], [], captured_jobs=0)
    assert access.status is CanadaAccess.NO_CURRENT_OPENING
    assert not hasattr(access, "tier")  # nothing here can write into a tier


def test_truncated_board_forbids_precise_scoring() -> None:
    a = assess_access(["Toronto, ON"] * 500, [False] * 500,
                      captured_jobs=500, reported_total=1815)
    assert a.capture is CaptureStatus.TRUNCATED
    assert a.scores_are_precise is False
    assert a.capture_rate == pytest.approx(500 / 1815)


def test_unknown_total_yields_no_fabricated_capture_rate() -> None:
    a = assess_access(["Toronto, ON"], [True], captured_jobs=1)
    assert a.capture_rate is None
    assert a.status is CanadaAccess.OPEN_STUDENT_ROLE


def test_failed_fetch_is_unknown_not_absent() -> None:
    a = assess_access([], [], captured_jobs=0, fetch_failed=True)
    assert a.status is CanadaAccess.UNKNOWN
    assert a.capture is CaptureStatus.FAILED
    assert "unknown, not absent" in a.note


def test_partial_scope_board_never_reads_as_complete() -> None:
    a = assess_access(["Toronto"] * 4, [False] * 4,
                      captured_jobs=4, board_scope_partial=True)
    assert a.capture is CaptureStatus.PARTIAL_SCOPE
    assert a.scores_are_precise is False


@pytest.mark.parametrize("raw,expected", [
    ("Toronto, ON", LocationClass.CANADA_EXPLICIT),
    ("Remote - Canada", LocationClass.CANADA_REMOTE),
    ("North America (Remote)", LocationClass.AMERICAS_REMOTE_NEEDS_REVIEW),
    ("San Francisco, CA", LocationClass.CANADA_NOT_ELIGIBLE),
    ("", LocationClass.UNKNOWN_LOCATION),
])
def test_location_classification(raw: str, expected: LocationClass) -> None:
    assert classify_location(raw) is expected


def test_us_only_role_is_not_treated_as_canadian_access() -> None:
    a = assess_access(["Seattle, WA", "New York, NY"], [True, True], captured_jobs=2)
    assert a.canada_roles == 0
    assert a.status is CanadaAccess.NO_CURRENT_OPENING
