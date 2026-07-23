"""Company registry — the tiering layer, served without touching the database.

This is deliberately stateless. The registry is a frozen assessment (see
`app/company/profiles.py`), not accumulated data, so it needs no persistence
and cannot go stale between syncs. The job layer that will consume it does
live in the database; this does not.

Three views are exposed rather than one ranking, because "where should my
applications go" and "what is worth wanting" are different questions with
substantially different answers. Every row in the value view carries the action
it implies, so a high rank there cannot be misread as an instruction to apply.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import require_token
from app.company.gate import GATED_OUT
from app.company.profiles import (
    ALL_PROFILES,
    BY_KEY,
    EXCLUSIONS,
    OFFER_ACCEPT_THRESHOLD,
    PERSONAL_BANDS,
    TIER_BANDS,
    VALUE_BANDS,
    CompanyProfile,
    View,
    adjustments,
    ranked,
    tier_counts,
)
from app.company.sources import BY_COMPANY as SOURCE_BY_COMPANY
from app.company.sources import coverage as source_coverage

router = APIRouter(prefix="/registry", tags=["registry"],
                   dependencies=[Depends(require_token)])

TIER_ORDER = ("S", "A", "B", "C", "D")


def _tier_for(p: CompanyProfile, view: View) -> str:
    if view is View.VALUE:
        return p.value_tier
    if view is View.PLATFORM:
        return p.platform_tier
    return p.personal_tier


def _score_for(p: CompanyProfile, view: View) -> float:
    if view is View.VALUE:
        return p.value_score
    if view is View.PLATFORM:
        return p.platform_score
    return p.personal_score


def _source_of(p: CompanyProfile) -> dict:
    """Where a posting actually comes from — including "a human has to go".

    Surfaced on every card so an employer we cannot reach stays visible. The
    previous design let missing connector coverage remove companies entirely.
    """
    s = SOURCE_BY_COMPANY.get(p.key)
    if s is not None:
        return {
            "status": s.status.value,
            "automatable": s.automatable,
            "careers_url": s.careers_url or None,
            "connector": s.connector,
            "observed_jobs": s.observed_jobs,
            "observed_canada": s.observed_canada,
            "observed_student_canada": s.observed_student_canada,
            "note": s.note or None,
            "probed_on": s.probed_on,
        }
    if p.boards:
        return {"status": "verified", "automatable": True, "careers_url": None,
                "connector": p.boards[0][0], "observed_jobs": None,
                "observed_canada": None, "observed_student_canada": None,
                "note": None, "probed_on": None}
    return {"status": "searching", "automatable": False, "careers_url": None,
            "connector": None, "observed_jobs": None, "observed_canada": None,
            "observed_student_canada": None,
            "note": "No source located yet — not reachable automatically or manually.",
            "probed_on": None}


def _card(p: CompanyProfile, view: View) -> dict:
    return {
        "key": p.key,
        "name": p.name,
        "tier": _tier_for(p, view),
        "score": round(_score_for(p, view), 1),
        # Both axes always travel with the row: a rank without them cannot be
        # acted on, because it does not say whether the constraint is reach or
        # worth.
        "value_score": round(p.value_score, 1),
        "access_score": round(p.access_score, 1),
        "priority_score": round(p.personal_score, 1),
        "platform_score": round(p.platform_score, 1),
        "value_tier": p.value_tier,
        "platform_tier": p.platform_tier,
        "priority_tier": p.personal_tier,
        "posture": p.posture.value,
        "action": p.value_view_action,
        "worth_taking_if_offered": p.worth_taking_if_offered,
        "safety_net": p.safety_net,
        "role_floor": p.role_floor,
        "adjusted": p.adjusted,
        "override_reason": p.adjustment_reason,
        "why": p.why,
        "tags": list(p.tags),
        "source": _source_of(p),
        "inputs": {
            "brand_ca": p.brand_ca, "brand_us": p.brand_us, "brand_cn": p.brand_cn,
            "tech": p.tech, "depth": p.depth, "role": p.role,
            "domain": p.domain, "founder": p.founder, "program": p.program,
        },
        "assessed_on": p.assessed_on,
        "valid_until": p.valid_until,
    }


@router.get("/companies")
async def list_companies(
    view: str = Query(View.APPLY, description="apply | value | platform"),
    tier: str | None = Query(None, description="filter to a single tier"),
    tag: str | None = Query(None),
    posture: str | None = Query(None),
) -> dict:
    try:
        v = View(view)
    except ValueError:
        raise HTTPException(422, f"unknown view {view!r}") from None

    rows = ranked(v)
    if tier:
        rows = [p for p in rows if _tier_for(p, v) == tier.upper()]
    if tag:
        rows = [p for p in rows if tag in p.tags]
    if posture:
        rows = [p for p in rows if p.posture.value == posture]

    groups: list[dict] = []
    for t in TIER_ORDER:
        members = [p for p in rows if _tier_for(p, v) == t]
        if members:
            groups.append({
                "tier": t,
                "count": len(members),
                "companies": [_card(p, v) for p in members],
            })

    return {
        "view": v.value,
        "total": len(rows),
        "groups": groups,
        "counts": {t: sum(1 for p in rows if _tier_for(p, v) == t)
                   for t in TIER_ORDER},
    }


@router.get("/company/{key}")
async def company_detail(key: str) -> dict:
    p = BY_KEY.get(key)
    if p is None:
        raise HTTPException(404, f"no company {key!r} in the registry")
    card = _card(p, View.APPLY)
    # Show the arithmetic, not just the result. A score nobody can reproduce
    # is an opinion wearing a number.
    card["breakdown"] = {
        "brand": round(p.brand, 3),
        "value_terms": {
            "brand": round(30.0 * p.brand, 1),
            "tech": round(25.0 * p.tech / 3.0, 1),
            "domain": round(25.0 * p.domain / 3.0, 1),
            "founder": round(20.0 * p.founder / 3.0, 1),
        },
        "access_terms": {
            "depth": round(100 * 0.40 * p.depth / 3.0, 1),
            "role": round(100 * 0.40 * p.role / 3.0, 1),
            "program": round(100 * 0.20 * p.program / 3.0, 1),
        },
        "platform_terms": {
            "brand": round(72.0 * p.brand, 1),
            "program": round(16.0 * p.program / 3.0, 1),
            "tech_bonus": round(4.0 * p.tech, 1),
        },
        "algo_platform_tier": p.algo_tier,
        "algo_priority_tier": p.algo_personal_tier,
    }
    return card


@router.get("/meta")
async def meta() -> dict:
    """Everything needed to read the rankings honestly, in one place."""
    return {
        "total_rated": len(ALL_PROFILES),
        "counts": {
            "apply": tier_counts("personal"),
            "platform": tier_counts("platform"),
        },
        "bands": {
            "platform": [{"floor": f, "tier": t} for f, t in TIER_BANDS],
            "apply": [{"floor": f, "tier": t} for f, t in PERSONAL_BANDS],
            "value": [{"floor": f, "tier": t} for f, t in VALUE_BANDS],
        },
        "offer_accept_threshold": OFFER_ACCEPT_THRESHOLD,
        "formulas": {
            "value": "30% brand + 25% tech + 25% domain + 20% founder",
            "access": "40% depth + 40% role + 20% program",
            "apply": "sqrt(value * access)",
            "platform": "72*brand + 16*(program/3) + 4*tech",
            "brand": "(ca*0.60 + us*0.25 + cn*0.15) / 3",
        },
        "adjustments": [
            {"name": p.name,
             "algo_priority_tier": p.algo_personal_tier,
             "final_priority_tier": p.personal_tier,
             "algo_platform_tier": p.algo_tier,
             "final_platform_tier": p.platform_tier,
             "reason": p.adjustment_reason}
            for p in adjustments()
        ],
        "excluded_categories": EXCLUSIONS,
        "gated_categories": {k: {"gate": v.gate.value, "reason": v.reason}
                             for k, v in GATED_OUT.items()},
        "source_coverage": {
            "with_known_board": sum(1 for p in ALL_PROFILES if p.boards),
            "without_source": sum(1 for p in ALL_PROFILES if not p.boards),
            "by_status": source_coverage(),
        },
    }
