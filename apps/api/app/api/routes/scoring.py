from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_token
from app.company.intelligence import CompanyDimension
from app.db.session import get_session
from app.models.ops import AuditLog
from app.models.ranking_v2 import PairwisePreference
from app.models.sourcing import Job
from app.models.user import User
from app.ranking.modes import RankingMode
from app.services.pool import REFRESH
from app.services.scoring_v2 import (
    _company_evidence,
    latest_scores,
    score_all_jobs,
    score_job,
)

router = APIRouter(prefix="/scoring", tags=["scoring"], dependencies=[Depends(require_token)])


async def _sole_user_id(session: AsyncSession) -> str:
    uid = (await session.execute(select(User.id).limit(1))).scalar_one_or_none()
    if not uid:
        raise HTTPException(400, "no user exists yet")
    return uid


@router.post("/recompute")
async def recompute(
    mode: str = Body(default="internship", embed=True),
    only_unscored: bool = Body(default=False, embed=True),
    limit: int | None = Body(default=None, embed=True),
    offset: int = Body(default=0, embed=True),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Recompute v2 priority. Legacy v1 rows are left untouched.

    `only_unscored` skips postings that already carry a score for this user and
    mode, which makes the call resumable: a pass that is interrupted can simply
    be run again and will pick up where it stopped rather than starting over.
    """
    try:
        rmode = RankingMode(mode)
    except ValueError as exc:
        raise HTTPException(400, f"unknown ranking mode: {mode}") from exc
    # A pool refresh rescores the same rows from its own session. Since scoring
    # became an upsert against a unique constraint, two concurrent writers no
    # longer produce a harmless duplicate — the loser hits IntegrityError. One
    # owner, one rescan at a time.
    if REFRESH.running:
        raise HTTPException(
            409,
            "a pool refresh is rescoring right now; wait for it to finish "
            "(GET /pool/refresh/status) and try again",
        )
    user_id = await _sole_user_id(session)
    result = await score_all_jobs(
        session, user_id, mode=rmode, only_unscored=only_unscored,
        limit=limit, offset=offset
    )
    session.add(AuditLog(actor="user", action="recompute_scores",
                         entity_type="scoring", summary=str(result)))
    await session.commit()
    return result


@router.get("/jobs")
async def scored_jobs(
    limit: int = Query(100, le=300),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Jobs with their v2 multi-dimensional scores, ordered by priority."""
    jobs = (
        await session.execute(
            select(Job).where(Job.deleted_at.is_(None)).limit(limit)
        )
    ).scalars().all()
    scores = await latest_scores(session, [j.id for j in jobs])

    items = []
    for j in jobs:
        s = scores.get(j.id)
        items.append({
            "job_id": j.id,
            "title": j.title,
            "apply_url": j.canonical_application_url,
            "source_status": j.source_status,
            "freshness": j.freshness_score,
            "scored": s is not None,
            **(s or {}),
        })
    items.sort(key=lambda i: -(i.get("application_priority") or -1))
    return {"count": len(items), "items": items,
            "note": "application_priority is 0-100 priority, NOT a match percentage"}


@router.get("/jobs/{job_id}")
async def scored_job_detail(
    job_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """Full explanation: contribution breakdown, coverage, company intelligence."""
    job = await session.get(Job, job_id)
    if not job or job.deleted_at:
        raise HTTPException(404, "job not found")
    user_id = await _sole_user_id(session)

    result = await score_job(session, job, user_id, persist=False)
    evidence = await _company_evidence(session, job.company_id)

    from app.company.intelligence import assess_company
    company = assess_company(evidence)

    return {
        "job": {"id": job.id, "title": job.title,
                "apply_url": job.canonical_application_url,
                "description": job.description_text},
        "scores": result.as_dict(),
        "why_it_ranks_here": {
            # 2026-07-24: no more base/tier-adjustment/floor split — a plain
            # weighted sum of the six dimensions, contributions already
            # reconcile to final_priority (see app/ranking/priority.py).
            "contributions": result.contributions,
            "final_priority": result.application_priority,
            "action_urgency": result.action_urgency,
            "application_effort_minutes": result.application_effort_minutes,
            "rule": result.interaction_rule,
        },
        "evidence_coverage": {
            "overall": result.evidence_coverage,
            "company_coverage": company.evidence_coverage,
            "rating_status": company.rating_status,
            "fit_coverage": result.current_candidate_fit.coverage,
            "fit_known_evidence": result.current_candidate_fit.known_evidence,
            "known": [d.dimension.value for d in company.dimensions if d.score is not None],
            "unknown": [d.dimension.value for d in company.dimensions if d.score is None],
            "notes": company.notes,
            "unknowns": result.unknowns,
        },
        "company_intelligence": {
            "estimated_tier": company.estimated_tier,
            "rated_tier": company.rated_tier,
            "display_tier": company.display_tier,
            "rating_status": company.rating_status,
            "known_evidence_score": company.known_evidence_score,
            "conservative_score": company.conservative_score,
            "dimensions": [
                {"dimension": d.dimension.value, "score": d.score,
                 "confidence": d.confidence, "evidence_count": d.evidence_count,
                 "evidence": d.top_evidence}
                for d in company.dimensions
            ],
            "risk": None if not company.risk else {
                "level": company.risk.level.value,
                "evidence_quality": company.risk.evidence_quality,
                "signal_count": company.risk.signal_count,
                "manual_research_required": company.risk.manual_research_required,
                "flags": company.risk.flags,
            },
        },
        "role_classification": {
            "final_category": result.role_band,
            "role_type": result.role_type,
        },
    }


@router.get("/compare")
async def compare(
    a: str = Query(...), b: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Put two jobs side by side. The user's choice becomes a Pairwise Preference."""
    user_id = await _sole_user_id(session)
    out = []
    for jid in (a, b):
        job = await session.get(Job, jid)
        if not job:
            raise HTTPException(404, f"job {jid} not found")
        r = await score_job(session, job, user_id, persist=False)
        out.append({"job_id": job.id, "title": job.title, **r.as_dict()})
    return {"a": out[0], "b": out[1]}


@router.post("/preference")
async def record_preference(
    chosen_job_id: str = Body(...),
    rejected_job_id: str = Body(...),
    note: str | None = Body(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Record which job the user preferred — the calibration signal for
    platform-vs-fit. Never auto-applied to weights."""
    user_id = await _sole_user_id(session)
    scores = await latest_scores(session, [chosen_job_id, rejected_job_id])
    c, r = scores.get(chosen_job_id, {}), scores.get(rejected_job_id, {})

    pref = PairwisePreference(
        user_id=user_id, chosen_job_id=chosen_job_id, rejected_job_id=rejected_job_id,
        chosen_tier=c.get("company_tier"), rejected_tier=r.get("company_tier"),
        chosen_band=c.get("role_category"), rejected_band=r.get("role_category"),
        context="compare", note=note,
    )
    session.add(pref)
    session.add(AuditLog(actor="user", action="pairwise_preference",
                         entity_type="job", entity_id=chosen_job_id,
                         summary=f"chose {chosen_job_id} over {rejected_job_id}"))
    await session.commit()
    return {"recorded": True, "id": pref.id, "at": datetime.now(UTC)}


@router.get("/dimensions")
async def dimensions() -> dict:
    return {"company_dimensions": [d.value for d in CompanyDimension]}
