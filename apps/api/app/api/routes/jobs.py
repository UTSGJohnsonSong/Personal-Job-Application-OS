from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_token
from app.db.session import get_session
from app.models.matching import JobMatch
from app.models.sourcing import Job

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_token)])


def _job_dto(job: Job) -> dict:
    return {
        "id": job.id,
        "title": job.title,
        "company_id": job.company_id,
        "remote_mode": job.remote_mode,
        "official_source_url": job.official_source_url,
        "canonical_application_url": job.canonical_application_url,
        "source_status": job.source_status,
        "current_status": job.current_status,
        "inbox_category": job.inbox_category,
        "freshness_score": job.freshness_score,
        "source_priority": job.source_priority,
        "first_seen_at": job.first_seen_at,
        "last_verified_at": job.last_verified_at,
        "application_deadline": job.application_deadline,
        "duplicate_group_id": job.duplicate_group_id,
    }


@router.get("")
async def list_jobs(
    category: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> dict:
    stmt = select(Job).where(Job.deleted_at.is_(None))
    if category:
        stmt = stmt.where(Job.inbox_category == category)
    stmt = stmt.order_by(Job.freshness_score.desc()).limit(limit).offset(offset)
    jobs = (await session.execute(stmt)).scalars().all()
    return {"items": [_job_dto(j) for j in jobs], "count": len(jobs)}


@router.get("/{job_id}")
async def get_job(job_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    job = await session.get(Job, job_id)
    if not job or job.deleted_at:
        raise HTTPException(404, "job not found")
    match = (
        await session.execute(
            select(JobMatch).where(JobMatch.job_id == job_id)
            .order_by(JobMatch.created_at.desc())
        )
    ).scalars().first()
    dto = _job_dto(job)
    dto["description_text"] = job.description_text
    if match:
        dto["match"] = {
            "total_score": match.total_score,
            "strategy": match.strategy,
            "why_recommended": match.why_recommended,
            "why_not": match.why_not,
            "suggested_minutes": match.suggested_minutes,
        }
    return dto
