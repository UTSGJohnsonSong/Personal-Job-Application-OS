"""Eligibility Gate — separated from ranking entirely.

Previously `hard_eligibility` was BOTH a weighted dimension (3.0) AND a hard cap
(`min(total, 0.15)`) — double counting with confused semantics. Now eligibility
only answers "may the user apply?" and never contributes positive score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.eligibility.engine import EligibilityReport, Verdict


class Gate(StrEnum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    FAIL = "FAIL"


@dataclass
class GateResult:
    gate: Gate
    verdict: str
    reasons: list[str] = field(default_factory=list)
    jd_evidence: list[str] = field(default_factory=list)
    context_evidence: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    needs_user_confirmation: bool = False
    low_risk_note: str = ""

    @property
    def blocks_queue(self) -> bool:
        """FAIL never enters the normal high-priority queue."""
        return self.gate is Gate.FAIL

    @property
    def requires_manual_review(self) -> bool:
        return self.gate is Gate.REVIEW


def evaluate_gate(report: EligibilityReport) -> GateResult:
    """Map the 5-level verdict onto PASS / REVIEW / FAIL."""
    mapping = {
        Verdict.ELIGIBLE: Gate.PASS,
        Verdict.LIKELY_ELIGIBLE: Gate.PASS,
        Verdict.UNCERTAIN: Gate.REVIEW,
        Verdict.LIKELY_INELIGIBLE: Gate.REVIEW,
        Verdict.INELIGIBLE: Gate.FAIL,
    }
    gate = mapping[report.verdict]

    # likely_ineligible escalates to FAIL when there is a concrete conflicting
    # fact rather than merely thin evidence.
    if report.verdict is Verdict.LIKELY_INELIGIBLE and report.conflicts:
        gate = Gate.FAIL

    note = ""
    if report.verdict is Verdict.LIKELY_ELIGIBLE:
        note = "PASS with low-risk caveat: " + "; ".join(report.unknowns[:2])

    return GateResult(
        gate=gate,
        verdict=report.verdict.value,
        reasons=report.reasons,
        jd_evidence=report.jd_evidence,
        context_evidence=report.context_evidence,
        unknowns=report.unknowns,
        conflicts=report.conflicts,
        needs_user_confirmation=report.needs_user_confirmation,
        low_risk_note=note,
    )
