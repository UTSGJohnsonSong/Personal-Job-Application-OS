"""Applicability gate — runs BEFORE tiering, not as part of it.

A company he could never actually apply to does not belong at the bottom of the
ranking; it belongs outside it. Tier D means "weak platform", not "impossible".
Mixing the two makes D meaningless and buries the genuinely weak-but-real
options underneath a pile of noise.

So the pipeline is:

    universe -> GATE -> tiering (S..D) -> source registry -> ingestion

Anything the gate rejects carries a reason and stays visible in a separate list,
because a silent exclusion is how the last company universe quietly became
"whatever ATS my connectors happened to support".

Gate outcomes are about *structural* impossibility only. "Hard to get" is not a
gate — that is what the tiers and the ranking are for.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Gate(StrEnum):
    PASS = "pass"
    NO_CANADIAN_HIRING = "no_canadian_hiring"
    WORK_AUTH_MISMATCH = "work_auth_mismatch"
    CLEARANCE_REQUIRED = "clearance_required"
    NO_ENTRY_LEVEL = "no_entry_level"
    DOMAIN_REJECTED = "domain_rejected"
    DEFUNCT = "defunct"


@dataclass(frozen=True)
class GateResult:
    gate: Gate
    reason: str

    @property
    def passed(self) -> bool:
        return self.gate is Gate.PASS

    @property
    def tierable(self) -> bool:
        """Only companies that pass the gate are ever assigned a tier."""
        return self.passed


PASS = GateResult(Gate.PASS, "structurally applicable")


# The candidate is a Canadian PR with co-op eligibility and NO US work
# authorisation. That single fact drives most gate rejections below.
def evaluate(
    *,
    name: str,
    hires_in_canada: bool,
    remote_open_to_canada: bool = False,
    requires_us_authorization: bool = False,
    requires_clearance: bool = False,
    hires_students: bool = True,
    domain_rejected: str | None = None,
    defunct: bool = False,
) -> GateResult:
    if defunct:
        return GateResult(Gate.DEFUNCT, f"{name} no longer operates as an employer")
    if domain_rejected:
        return GateResult(Gate.DOMAIN_REJECTED, domain_rejected)
    if requires_clearance:
        return GateResult(
            Gate.CLEARANCE_REQUIRED,
            "requires a security clearance tied to citizenship or residency "
            "duration he does not yet meet")
    if requires_us_authorization and not hires_in_canada:
        return GateResult(
            Gate.WORK_AUTH_MISMATCH,
            "hires only into roles requiring US work authorisation, which he "
            "does not hold")
    if not hires_in_canada and not remote_open_to_canada:
        return GateResult(
            Gate.NO_CANADIAN_HIRING,
            "no Canadian entity and no remote roles open to Canada — he cannot "
            "be employed here at all")
    if not hires_students:
        return GateResult(
            Gate.NO_ENTRY_LEVEL,
            "no student, co-op, internship or new-graduate hiring of any kind")
    return PASS


# ---------------------------------------------------------------------------
# Structural rejections recorded once, so the omission stays auditable.
# These are categories, not individual companies, because the reason applies to
# every member of the category identically.
# ---------------------------------------------------------------------------
GATED_OUT: dict[str, GateResult] = {
    "US federal contractors and cleared defence work":
        GateResult(Gate.CLEARANCE_REQUIRED,
                   "US clearance requires US citizenship; structurally closed"),
    "US-only startups with no Canadian entity (most Series A/B in SF and NYC)":
        GateResult(Gate.NO_CANADIAN_HIRING,
                   "no Canadian payroll entity, and their remote postings are "
                   "US-only for tax and equity reasons"),
    "Canadian Armed Forces, CSIS, CSE":
        GateResult(Gate.CLEARANCE_REQUIRED,
                   "enhanced reliability or Top Secret clearance with residency "
                   "requirements he does not yet satisfy"),
    "Mining, oil, gas and resource extraction":
        GateResult(Gate.DOMAIN_REJECTED,
                   "no analyst or product path he wants, and nothing that "
                   "compounds toward his stated direction"),
    "Grocery, apparel and general retail operations":
        GateResult(Gate.DOMAIN_REJECTED,
                   "store and supply-chain reporting seats are exactly the "
                   "no-customer-contact trap his own analysis rules out"),
    "IT outsourcing and body shops":
        GateResult(Gate.DOMAIN_REJECTED,
                   "staffed onto client maintenance; no product surface"),
    "Big-four audit and tax streams":
        GateResult(Gate.DOMAIN_REJECTED,
                   "not a data or product path; their AI arms are rated "
                   "separately if and when he wants them"),
    "Management consulting generalist streams":
        GateResult(Gate.DOMAIN_REJECTED,
                   "strong brands, but the entry seat leads away from building"),
    "Semiconductor and EDA design houses":
        GateResult(Gate.DOMAIN_REJECTED,
                   "deep hardware paths with no analyst or product entry point"),
    "Companies that have exited Canada or wound down":
        GateResult(Gate.DEFUNCT,
                   "kept as a named category so a stale record never silently "
                   "reappears as a live target"),
}
