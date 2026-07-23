from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_token
from app.applications.recommendation import build_application_set, redundancy_risk
from app.company.portfolio import companies_requiring_action
from app.db.session import get_session
from app.models.company_inbox import (
    RecommendedApplicationSet,
    RecommendedApplicationSetItem,
)
from app.models.ops import AuditLog
from app.models.ranking_v2 import PairwisePreference
from app.services.inbox import (
    CALCULATION_VERSION,
    RANKING_FORMULA_VERSION,
    _sole_user_id,
    company_stats,
    dashboard_metrics,
    global_view,
    load_companies,
    rebuild_inbox,
    tier_view,
)

router = APIRouter(prefix="/inbox", tags=["inbox"], dependencies=[Depends(require_token)])


async def _uid(session: AsyncSession) -> str:
    uid = await _sole_user_id(session)
    if not uid:
        raise HTTPException(400, "no user exists yet")
    return uid


@router.post("/rebuild")
async def rebuild(session: AsyncSession = Depends(get_session)) -> dict:
    """Recompute company organisation + recommendation sets, and persist them."""
    user_id = await _uid(session)
    result = await rebuild_inbox(session, user_id)
    session.add(AuditLog(actor="user", action="inbox_rebuild",
                         entity_type="inbox", summary=str(result)))
    await session.commit()
    return result


@router.get("/by-tier")
async def by_tier(session: AsyncSession = Depends(get_session)) -> dict:
    """View 1 — companies grouped by tier. Provisional gets its own bucket."""
    user_id = await _uid(session)
    companies = await load_companies(session, user_id)
    return {
        "view": "by_company_tier",
        "groups": tier_view(companies),
        "note": "Tier organises companies; Application Priority orders roles.",
    }


@router.get("/global")
async def global_priority(
    limit: int = Query(100, le=500), session: AsyncSession = Depends(get_session)
) -> dict:
    """View 2 — a single queue across all tiers, ordered by priority only."""
    user_id = await _uid(session)
    companies = await load_companies(session, user_id)
    return {
        "view": "global_priority",
        "items": global_view(companies, limit=limit),
        "note": "Ordered purely by Application Priority (0-100). Not a match %.",
    }


@router.get("/company/{company_id}")
async def company_detail(
    company_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """Company detail: overview, roles, the recommended set and its reasons."""
    user_id = await _uid(session)
    companies = await load_companies(session, user_id)
    entry = next((c for c in companies if c.company_id == company_id), None)
    if entry is None:
        raise HTTPException(404, "company not found or has no scored roles")

    result = build_application_set(entry)
    applied = entry.applied_roles

    def role_dto(r) -> dict:
        return {
            "job_id": r.job_id, "title": r.title, "role_band": r.role_band,
            "role_type": r.role_type, "role_family": r.family.value,
            "eligibility": r.eligibility,
            "application_priority": round(r.application_priority, 1),
            "company_platform_value": round(r.company_platform_value, 1),
            "role_strategic_value": round(r.role_strategic_value, 1),
            "current_fit": round(r.current_fit, 1),
            "team_quality": round(r.team_quality, 1),
            "career_optionality": round(r.career_optionality, 1),
            "evidence_coverage": round(r.evidence_coverage, 3),
            "similarity_group": r.similarity_group_id,
            "location": r.location, "department": r.department,
            "is_official": r.is_official, "apply_url": r.canonical_url,
            "discovery_url": r.discovery_url,
            "is_student_role": r.is_student_role,
            "recommendation": r.recommendation,
        }

    ranked = entry.ranked_roles()
    internal_rank = {r.job_id: i + 1 for i, r in enumerate(ranked)}

    return {
        "overview": {
            "company_id": entry.company_id, "name": entry.name,
            "tier": entry.tier, "tier_display": entry.tier_display,
            "provisional": entry.provisional,
            "platform_value": round(entry.platform_value, 1),
            "evidence_coverage": round(entry.evidence_coverage, 3),
            "official_source_coverage": round(entry.official_source_coverage, 3),
            "last_synced_at": entry.last_checked,
            "high_potential_unrated": entry.high_potential_unrated,
            **company_stats(entry),
        },
        "top_recommended_roles": [role_dto(r) for r in entry.top_roles()],
        "all_relevant_roles": [role_dto(r) for r in ranked],
        "student_early_careers": [role_dto(r) for r in entry.student_roles],
        "applied_roles": [role_dto(r) for r in applied],
        "recommended_application_set": {
            "limit": result.limit,
            "over_limit": result.over_limit,
            "already_applied": result.already_applied,
            "notes": result.notes,
            "recommended": [
                {
                    "rank": rec.rank,
                    "company_internal_rank": internal_rank.get(rec.role.job_id),
                    "reason": rec.reason,
                    **role_dto(rec.role),
                }
                for rec in result.recommended
            ],
            "excluded": [
                {
                    "reason": exc.reason,
                    "superseded_by": exc.superseded_by,
                    "redundancy_risk": max(
                        (redundancy_risk(exc.role, rec.role)
                         for rec in result.recommended), default=0.0),
                    "duplicates_applied_role": any(
                        redundancy_risk(exc.role, a) >= 0.75 for a in applied),
                    **role_dto(exc.role),
                }
                for exc in result.excluded
            ],
        },
        "official_sources": {
            "roles_with_official_link": sum(1 for r in entry.relevant_roles
                                            if r.is_official),
            "roles_third_party_only": [role_dto(r) for r in entry.relevant_roles
                                       if not r.is_official],
        },
        "calculation": {
            "calculation_version": CALCULATION_VERSION,
            "ranking_formula_version": RANKING_FORMULA_VERSION,
        },
    }


@router.get("/compare")
async def compare_roles(
    a: str = Query(...), b: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Cross-tier comparison of two roles, with an explanation."""
    user_id = await _uid(session)
    companies = await load_companies(session, user_id)
    lookup = {r.job_id: (c, r) for c in companies for r in c.roles}
    for jid in (a, b):
        if jid not in lookup:
            raise HTTPException(404, f"role {jid} not found or unscored")

    def side(jid: str) -> dict:
        c, r = lookup[jid]
        return {
            "job_id": r.job_id, "title": r.title, "company": c.name,
            "company_tier": c.tier_display,
            "company_platform_value": round(r.company_platform_value, 1),
            "role_strategic_value": round(r.role_strategic_value, 1),
            "team_project_quality": round(r.team_quality, 1),
            "current_fit": round(r.current_fit, 1),
            "career_optionality": round(r.career_optionality, 1),
            "evidence_coverage": round(r.evidence_coverage, 3),
            "application_priority": round(r.application_priority, 1),
            "role_band": r.role_band,
            "eligibility": r.eligibility,
            "apply_url": r.canonical_url,
        }

    left, right = side(a), side(b)
    hi, lo = (left, right) if left["application_priority"] >= right["application_priority"] \
        else (right, left)

    reasons: list[str] = []
    if hi["company_platform_value"] < lo["company_platform_value"]:
        reasons.append(
            f"{hi['title']} ranks higher despite {lo['company']} having the stronger "
            f"platform ({lo['company_platform_value']:.0f} vs "
            f"{hi['company_platform_value']:.0f}) — its role strategic value and "
            "current fit more than compensate."
        )
    for label, key in (("role strategic value", "role_strategic_value"),
                       ("current fit", "current_fit"),
                       ("team quality", "team_project_quality")):
        if hi[key] > lo[key] + 5:
            reasons.append(f"higher {label} ({hi[key]:.0f} vs {lo[key]:.0f})")
    if not reasons:
        reasons.append("the two are close; the difference comes from combined weights")

    return {"a": left, "b": right, "leader": hi["job_id"], "explanation": reasons}


@router.post("/compare/choose")
async def record_choice(
    chosen_job_id: str = Body(...), rejected_job_id: str = Body(...),
    note: str | None = Body(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Record which role the user preferred — the platform-vs-fit calibration."""
    user_id = await _uid(session)
    companies = await load_companies(session, user_id)
    lookup = {r.job_id: (c, r) for c in companies for r in c.roles}
    chosen = lookup.get(chosen_job_id)
    rejected = lookup.get(rejected_job_id)

    pref = PairwisePreference(
        user_id=user_id, chosen_job_id=chosen_job_id, rejected_job_id=rejected_job_id,
        chosen_tier=chosen[0].tier if chosen else None,
        rejected_tier=rejected[0].tier if rejected else None,
        chosen_band=chosen[1].role_band if chosen else None,
        rejected_band=rejected[1].role_band if rejected else None,
        context="cross_tier_compare", note=note,
    )
    session.add(pref)
    session.add(AuditLog(actor="user", action="pairwise_preference",
                         entity_type="job", entity_id=chosen_job_id,
                         summary=f"chose {chosen_job_id} over {rejected_job_id}"))
    await session.commit()
    return {"recorded": True, "id": pref.id, "at": datetime.now(UTC)}


@router.get("/dashboard")
async def inbox_dashboard(session: AsyncSession = Depends(get_session)) -> dict:
    user_id = await _uid(session)
    companies = await load_companies(session, user_id)
    actions = companies_requiring_action(companies)
    return {
        "metrics": dashboard_metrics(companies),
        "top_companies_requiring_action": [
            {
                "company_id": c.company_id, "name": c.name,
                "tier": c.tier_display, "reasons": reasons,
                "best_priority": round(c.best_priority, 1),
            }
            for c, reasons in actions[:10]
        ],
    }


@router.get("/stored-sets")
async def stored_sets(session: AsyncSession = Depends(get_session)) -> dict:
    """Persisted recommendation sets — proof the decisions are not ad hoc."""
    sets = (
        await session.execute(
            select(RecommendedApplicationSet)
            .order_by(RecommendedApplicationSet.calculated_at.desc())
        )
    ).scalars().all()
    out = []
    for s in sets:
        items = (
            await session.execute(
                select(RecommendedApplicationSetItem)
                .where(RecommendedApplicationSetItem.set_id == s.id)
            )
        ).scalars().all()
        out.append({
            "set_id": s.id, "company_id": s.company_id,
            "company_tier_display": s.company_tier_display,
            "calculation_version": s.calculation_version,
            "calculated_at": s.calculated_at, "expires_at": s.expires_at,
            "limit": s.recommended_limit, "over_limit": s.over_limit,
            "user_override": s.user_override, "override_reason": s.override_reason,
            "evidence_snapshot": s.evidence_snapshot, "notes": s.notes,
            "recommended": [
                {"rank": i.rank, "title": i.title, "reason": i.reason,
                 "priority": i.application_priority, "family": i.role_family,
                 "similarity_group": i.similarity_group_key}
                for i in items if i.status == "recommended"
            ],
            "excluded": [
                {"title": i.title, "reason": i.reason,
                 "superseded_by": i.superseded_by,
                 "redundancy_risk": i.redundancy_risk,
                 "duplicates_applied_role": i.duplicates_applied_role}
                for i in items if i.status == "excluded"
            ],
        })
    return {"count": len(out), "sets": out}
