"""The official source registry, and the rule that unreachable != removed."""

from __future__ import annotations

from app.company.profiles import BY_KEY
from app.company.sources import (
    ALL_SOURCES,
    BY_COMPANY,
    SourceStatus,
    automatable_sources,
    coverage,
    manual_queue,
)


def test_every_source_points_at_a_company_in_the_registry() -> None:
    for s in ALL_SOURCES:
        assert s.company_key in BY_KEY, s.company_key


def test_one_source_record_per_company() -> None:
    keys = [s.company_key for s in ALL_SOURCES]
    assert len(keys) == len(set(keys))


def test_unreachable_companies_are_kept_not_dropped() -> None:
    """Connector coverage must never decide which employers exist.

    Amazon, Google, Microsoft and RBC were absent from an earlier ranking for
    exactly this reason: no connector reached them, so they were never ranked.
    """
    manual = {s.company_key for s in manual_queue()}
    for key in ("amazon", "google", "microsoft", "shopify", "rbc"):
        assert key in manual, key
        assert key in BY_KEY  # still rated
    for s in manual_queue():
        # A manual entry is only useful if it says where a human should go.
        # BioAdvance is the one open case and says so in its note.
        assert s.careers_url or s.note, s.company_key


def test_verified_sources_carry_observations() -> None:
    """A source claimed as verified has to show what the probe actually saw."""
    for s in ALL_SOURCES:
        if s.status is SourceStatus.VERIFIED:
            assert s.connector and s.external_id, s.company_key
            assert s.observed_jobs and s.observed_jobs > 0, s.company_key
            assert s.observed_canada is not None, s.company_key
            assert s.probed_on, s.company_key


def test_partial_boards_are_not_read_as_complete() -> None:
    """SAP answers with 867 postings and 4 Canadian ones; its co-op intake is
    published elsewhere, so absence on this board proves nothing."""
    sap = BY_COMPANY["sap"]
    assert sap.status is SourceStatus.PARTIAL
    assert sap.automatable  # still worth syncing
    assert "not on this board" in sap.note


def test_manual_only_is_never_treated_as_automatable() -> None:
    for s in manual_queue():
        assert not s.automatable
        assert s.connector is None


def test_false_positive_boards_were_rejected_not_recorded() -> None:
    """Slug guessing produced boards belonging to other companies. Those are
    recorded as manual with the reason, never as a working source."""
    for key in ("lightspeed", "uber"):
        s = BY_COMPANY[key]
        assert s.status is SourceStatus.MANUAL_ONLY
        assert "different company" in s.note or "not Uber" in s.note


def test_coverage_accounts_for_every_source() -> None:
    assert sum(coverage().values()) == len(ALL_SOURCES)
    assert len(automatable_sources()) + len(manual_queue()) == len(ALL_SOURCES)


def test_thomson_reuters_records_the_connector_bug_it_exposed() -> None:
    tr = BY_COMPANY["thomsonreuters"]
    assert tr.observed_jobs == 486
    assert tr.observed_canada and tr.observed_canada > 0
    assert "bulletFields" in tr.note
