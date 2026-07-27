"""Accented place names, and whole-region strings, must reach the gate.

Greenhouse returns "Zürich, CH". The foreign-location pattern spells it
"zurich", so the umlaut made it miss, the posting classified as
UNKNOWN_LOCATION, and unknown is only a REVIEW — not the hard FAIL an
unreachable country deserves. The role then sat at the top of the board marked
"needs a look", which is the opposite of what a location check is for.

The same silence covered "Europe" and "Middle East", which were not in the
pattern at all, and any accented city: Montréal, São Paulo, Bogotá.

These tests are written against the literal strings the boards emit, so a
future edit to the pattern cannot quietly reintroduce the class.
"""

from __future__ import annotations

import pytest

from app.company.access import LocationClass, classify_location, preferred_location

NOT_ELIGIBLE = LocationClass.CANADA_NOT_ELIGIBLE


@pytest.mark.parametrize(
    "raw",
    [
        "Zürich, CH",      # the one that was actually on screen
        "Zurich, CH",      # and its unaccented twin, which always worked
        "Zug",
        "Gothenburg",
        "São Paulo",
        "Bogotá",
        "Europe",          # a whole region is not ambiguous for this candidate
        "EMEA",
        "Middle East",
    ],
)
def test_unreachable_places_are_a_hard_fail_not_a_maybe(raw: str) -> None:
    assert classify_location(raw) is NOT_ELIGIBLE, (
        f"{raw!r} classified as {classify_location(raw).value}; anything other "
        f"than {NOT_ELIGIBLE.value} only earns a REVIEW and leaves the posting "
        f"sitting in the ranked list"
    )


@pytest.mark.parametrize(
    "raw",
    ["Montréal, QC", "Montreal", "Toronto, Ontario", "Oakville, Ontario - Canada"],
)
def test_folding_does_not_break_canadian_places(raw: str) -> None:
    assert classify_location(raw) in (
        LocationClass.CANADA_EXPLICIT,
        LocationClass.CANADA_REMOTE,
    )


def test_genuinely_unresolved_stays_unresolved() -> None:
    """Folding must not turn "I cannot tell" into "definitely not"."""
    assert classify_location("2 Locations") is LocationClass.UNKNOWN_LOCATION
    assert classify_location("") is LocationClass.UNKNOWN_LOCATION


def test_a_reachable_city_still_wins_over_an_accented_unreachable_one() -> None:
    """The pair that motivated all of this: one requisition, two cities."""
    assert preferred_location(["Zürich, CH", "Toronto, Ontario"]) == "Toronto, Ontario"
