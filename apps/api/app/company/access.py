"""Canada Access Status and capture honesty — the live layers.

These are deliberately separate from Platform Tier (app/company/profiles.py).
An earlier design forced any company with zero Canadian postings down to tier D,
which meant a tier could swing on a single requisition opening or closing. A
company that is a superb place to work but has nothing open in Toronto today is
`Platform S / Canada Access: NO_CURRENT_OPENING`, not `Platform D`.

Nothing here ever writes back into a tier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class CanadaAccess(StrEnum):
    """How reachable this employer is for a candidate who must work in Canada."""

    OPEN_STUDENT_ROLE = "open_student_role"        # Canadian student role open now
    OPEN_CANADA_ROLE = "open_canada_role"          # Canadian roles, none for students
    REMOTE_CANADA_OK = "remote_canada_ok"          # remote listings open to Canada
    NO_CURRENT_OPENING = "no_current_opening"      # Canadian site, nothing open now
    NO_CANADA_PRESENCE = "no_canada_presence"      # no evidence of Canadian hiring
    UNKNOWN = "unknown"                            # board not captured / unreadable


class CaptureStatus(StrEnum):
    """Was the board read completely? Anything else forbids a precise score."""

    COMPLETE = "complete"
    TRUNCATED = "truncated"        # a cap stopped us (e.g. Workday max_pages)
    PARTIAL_SCOPE = "partial_scope"  # board only carries part of the hiring
    FAILED = "failed"


class LocationClass(StrEnum):
    CANADA_EXPLICIT = "canada_explicit"
    CANADA_POSSIBLE = "canada_possible"            # "North America", multi-city
    CANADA_REMOTE = "canada_remote"
    AMERICAS_REMOTE_NEEDS_REVIEW = "americas_remote_needs_review"
    CANADA_NOT_ELIGIBLE = "canada_not_eligible"    # US-only, needs US authorisation
    UNKNOWN_LOCATION = "unknown_location"


_CANADA = re.compile(
    r"(toronto|canada|ontario|vancouver|montr|ottawa|waterloo|calgary|mississauga|"
    r"edmonton|halifax|winnipeg|kitchener|burnaby|markham|brampton|quebec|"
    r"\bON\b|\bBC\b|\bAB\b|\bQC\b|\bNS\b|\bMB\b)", re.I)
_US_ONLY = re.compile(
    r"(united states|\bU\.?S\.?A?\b|california|new york|texas|seattle|boston|"
    r"austin|denver|chicago|atlanta|san francisco)", re.I)
_REMOTE = re.compile(r"\bremote\b|\bdistributed\b|work from home", re.I)
_BROAD = re.compile(r"north america|americas|multiple locations|various", re.I)


def classify_location(raw: str) -> LocationClass:
    text = (raw or "").strip()
    if not text:
        return LocationClass.UNKNOWN_LOCATION
    canadian = bool(_CANADA.search(text))
    remote = bool(_REMOTE.search(text))
    if canadian:
        return LocationClass.CANADA_REMOTE if remote else LocationClass.CANADA_EXPLICIT
    if _BROAD.search(text):
        # "North America (Remote)" may or may not include Canada — never guess.
        return (LocationClass.AMERICAS_REMOTE_NEEDS_REVIEW if remote
                else LocationClass.CANADA_POSSIBLE)
    if _US_ONLY.search(text):
        return LocationClass.CANADA_NOT_ELIGIBLE
    if remote:
        return LocationClass.AMERICAS_REMOTE_NEEDS_REVIEW
    return LocationClass.UNKNOWN_LOCATION


@dataclass(frozen=True)
class AccessAssessment:
    status: CanadaAccess
    capture: CaptureStatus
    canada_roles: int
    canada_student_roles: int
    needs_review: int
    captured_jobs: int
    reported_total: int | None
    note: str

    @property
    def capture_rate(self) -> float | None:
        """None when unknowable — never fabricate a denominator."""
        if not self.reported_total:
            return None
        return min(1.0, self.captured_jobs / self.reported_total)

    @property
    def scores_are_precise(self) -> bool:
        return self.capture is CaptureStatus.COMPLETE


def assess_access(
    locations: list[str],
    student_flags: list[bool],
    *,
    captured_jobs: int,
    reported_total: int | None = None,
    fetch_failed: bool = False,
    board_scope_partial: bool = False,
) -> AccessAssessment:
    """Derive Canada access and record how trustworthy the read was."""
    if fetch_failed:
        return AccessAssessment(
            CanadaAccess.UNKNOWN, CaptureStatus.FAILED, 0, 0, 0,
            captured_jobs, reported_total,
            "board could not be read — access is unknown, not absent")

    classes = [classify_location(x) for x in locations]
    canada = sum(1 for c in classes
                 if c in (LocationClass.CANADA_EXPLICIT, LocationClass.CANADA_REMOTE))
    student_ca = sum(1 for c, s in zip(classes, student_flags, strict=False)
                     if s and c in (LocationClass.CANADA_EXPLICIT,
                                    LocationClass.CANADA_REMOTE))
    review = sum(1 for c in classes
                 if c in (LocationClass.AMERICAS_REMOTE_NEEDS_REVIEW,
                          LocationClass.CANADA_POSSIBLE,
                          LocationClass.UNKNOWN_LOCATION))
    remote_ok = any(c is LocationClass.CANADA_REMOTE for c in classes)

    if board_scope_partial:
        capture = CaptureStatus.PARTIAL_SCOPE
    elif reported_total and captured_jobs < reported_total:
        capture = CaptureStatus.TRUNCATED
    else:
        capture = CaptureStatus.COMPLETE

    if student_ca:
        status, note = (CanadaAccess.OPEN_STUDENT_ROLE,
                        f"{student_ca} Canadian student/co-op role(s) open now")
    elif canada:
        status, note = (CanadaAccess.OPEN_CANADA_ROLE,
                        f"{canada} Canadian role(s) open, none student-facing")
    elif remote_ok:
        status, note = (CanadaAccess.REMOTE_CANADA_OK, "remote roles open to Canada")
    elif review:
        status, note = (CanadaAccess.UNKNOWN,
                        f"{review} posting(s) need manual location review")
    elif capture is not CaptureStatus.COMPLETE:
        status, note = (CanadaAccess.UNKNOWN,
                        "board only partially captured — absence proves nothing")
    else:
        # Still not a judgment about the company, only about today's board.
        status, note = (CanadaAccess.NO_CURRENT_OPENING,
                        "no Canadian postings in this hiring cycle")

    return AccessAssessment(status, capture, canada, student_ca, review,
                            captured_jobs, reported_total, note)
