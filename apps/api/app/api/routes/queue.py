from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_token
from app.db.session import get_session
from app.models.application import Application
from app.models.matching import EligibilityResult, JobMatch
from app.models.ops import AuditLog
from app.models.sourcing import Job

router = APIRouter(prefix="/queue", tags=["queue"], dependencies=[Depends(require_token)])


async def _sole_user_id(session: AsyncSession) -> str:
    from app.models.user import User

    uid = (await session.execute(select(User.id).limit(1))).scalar_one_or_none()
    if not uid:
        raise HTTPException(400, "no user exists yet")
    return uid


@router.post("/{job_id}")
async def add_to_queue(
    job_id: str,
    note: str | None = Body(default=None, embed=True),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Put a job in the apply queue ("想投列表"). Idempotent."""
    job = await session.get(Job, job_id)
    if not job or job.deleted_at:
        raise HTTPException(404, "job not found")
    user_id = await _sole_user_id(session)

    app_row = (
        await session.execute(
            select(Application).where(
                Application.user_id == user_id, Application.job_id == job_id
            )
        )
    ).scalar_one_or_none()

    if app_row is None:
        app_row = Application(user_id=user_id, job_id=job_id, status="saved")
        session.add(app_row)
    if app_row.status == "discovered":
        app_row.status = "saved"
    app_row.queued_at = app_row.queued_at or datetime.now(UTC)
    if note:
        app_row.queue_note = note

    session.add(AuditLog(actor="user", action="queue_add", entity_type="job", entity_id=job_id))
    await session.commit()
    return {"application_id": app_row.id, "job_id": job_id, "queued_at": app_row.queued_at}


@router.delete("/{job_id}")
async def remove_from_queue(
    job_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    user_id = await _sole_user_id(session)
    app_row = (
        await session.execute(
            select(Application).where(
                Application.user_id == user_id, Application.job_id == job_id
            )
        )
    ).scalar_one_or_none()
    if not app_row:
        raise HTTPException(404, "not in queue")
    app_row.queued_at = None
    session.add(AuditLog(actor="user", action="queue_remove", entity_type="job", entity_id=job_id))
    await session.commit()
    return {"job_id": job_id, "queued": False}


@router.get("")
async def list_queue(session: AsyncSession = Depends(get_session)) -> dict:
    """The apply queue, ranked. This is what the agent reads at 投递时间.

    Order: manual queue_priority first (if set), then ranking score desc, then
    freshness desc. Already-submitted applications drop out of the queue.
    """
    user_id = await _sole_user_id(session)
    rows = (
        await session.execute(
            select(Application, Job)
            .join(Job, Job.id == Application.job_id)
            .where(
                Application.user_id == user_id,
                Application.queued_at.is_not(None),
                Application.submitted_at.is_(None),
            )
        )
    ).all()

    items = []
    for app_row, job in rows:
        match = (
            await session.execute(
                select(JobMatch)
                .where(JobMatch.job_id == job.id)
                .order_by(JobMatch.created_at.desc())
            )
        ).scalars().first()
        elig = (
            await session.execute(
                select(EligibilityResult)
                .where(EligibilityResult.job_id == job.id)
                .order_by(EligibilityResult.created_at.desc())
            )
        ).scalars().first()
        items.append(
            {
                "application_id": app_row.id,
                "job_id": job.id,
                "title": job.title,
                "status": app_row.status,
                "queue_note": app_row.queue_note,
                "queue_priority": app_row.queue_priority,
                "apply_url": job.canonical_application_url,
                "official_url": job.official_source_url,
                "deadline": job.application_deadline,
                "freshness": job.freshness_score,
                "source_status": job.source_status,
                "score": match.total_score if match else None,
                "strategy": match.strategy if match else None,
                "suggested_minutes": match.suggested_minutes if match else None,
                "why": match.why_recommended if match else [],
                "why_not": match.why_not if match else [],
                "eligibility": elig.verdict if elig else None,
                "needs_confirmation": elig.needs_user_confirmation if elig else False,
                "unknowns": elig.unknowns if elig else [],
            }
        )

    def sort_key(it: dict):
        manual = it["queue_priority"] if it["queue_priority"] is not None else 9999
        return (manual, -(it["score"] or 0), -(it["freshness"] or 0))

    items.sort(key=sort_key)

    # Surface anything that became un-applyable while sitting in the queue.
    warnings = [
        {"job_id": i["job_id"], "title": i["title"], "issue": "source no longer open"}
        for i in items
        if i["source_status"] not in ("open", "updated")
    ]
    return {"count": len(items), "items": items, "warnings": warnings}


@router.patch("/{job_id}/priority")
async def set_priority(
    job_id: str,
    priority: int | None = Body(default=None, embed=True),
    session: AsyncSession = Depends(get_session),
) -> dict:
    user_id = await _sole_user_id(session)
    app_row = (
        await session.execute(
            select(Application).where(
                Application.user_id == user_id, Application.job_id == job_id
            )
        )
    ).scalar_one_or_none()
    if not app_row:
        raise HTTPException(404, "not in queue")
    app_row.queue_priority = priority
    await session.commit()
    return {"job_id": job_id, "queue_priority": priority}
