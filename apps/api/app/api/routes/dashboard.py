from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_token
from app.db.session import get_session
from app.models.application import Application
from app.models.sourcing import Job

router = APIRouter(
    prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(require_token)]
)

_FUNNEL = [
    "discovered", "eligible", "shortlisted", "preparing", "ready_for_review",
    "submitted", "recruiter_contact", "assessment", "interview", "offer",
]


@router.get("/overview")
async def overview(session: AsyncSession = Depends(get_session)) -> dict:
    now = datetime.now(UTC)
    today = now - timedelta(days=1)
    week = now - timedelta(days=7)

    total_jobs = (await session.execute(
        select(func.count()).select_from(Job).where(Job.deleted_at.is_(None))
    )).scalar_one()
    new_today = (await session.execute(
        select(func.count()).select_from(Job).where(Job.first_seen_at >= today)
    )).scalar_one()
    applyable = (await session.execute(
        select(func.count()).select_from(Job).where(
            Job.source_status == "open", Job.deleted_at.is_(None)
        )
    )).scalar_one()

    # Applications by status.
    rows = (await session.execute(
        select(Application.status, func.count()).group_by(Application.status)
    )).all()
    by_status = {s: c for s, c in rows}

    submitted_week = (await session.execute(
        select(func.count()).select_from(Application).where(
            Application.submitted_at >= week
        )
    )).scalar_one()

    submitted = sum(
        by_status.get(s, 0)
        for s in ("submitted", "confirmation_received", "recruiter_contact",
                  "assessment", "phone_screen", "interview", "final_interview",
                  "offer", "accepted", "rejected")
    )
    replied = sum(
        by_status.get(s, 0)
        for s in ("recruiter_contact", "assessment", "phone_screen", "interview",
                  "final_interview", "offer", "accepted")
    )
    interviews = sum(
        by_status.get(s, 0)
        for s in ("interview", "final_interview", "offer", "accepted")
    )
    offers = by_status.get("offer", 0) + by_status.get("accepted", 0)

    def rate(n: int, d: int) -> float:
        return round(n / d, 3) if d else 0.0

    return {
        "totals": {
            "total_jobs": total_jobs,
            "new_today": new_today,
            "applyable": applyable,
            "submitted": submitted,
            "submitted_this_week": submitted_week,
            "replied": replied,
            "interviews": interviews,
            "offers": offers,
        },
        "by_status": by_status,
        "conversion": {
            "submit_to_reply": rate(replied, submitted),
            "reply_to_interview": rate(interviews, replied),
            "interview_to_offer": rate(offers, interviews),
        },
        "funnel": [{"stage": s, "count": by_status.get(s, 0)} for s in _FUNNEL],
    }


@router.get("/action-items")
async def action_items(session: AsyncSession = Depends(get_session)) -> dict:
    now = datetime.now(UTC)
    soon = now + timedelta(hours=48)
    two_weeks_ago = now - timedelta(days=14)

    waiting = (await session.execute(
        select(func.count()).select_from(Application).where(
            Application.status == "waiting_for_confirmation"
        )
    )).scalar_one()
    closing_soon = (await session.execute(
        select(func.count()).select_from(Job).where(
            Job.application_deadline.is_not(None),
            Job.application_deadline <= soon,
            Job.application_deadline >= now,
        )
    )).scalar_one()
    stale = (await session.execute(
        select(func.count()).select_from(Application).where(
            Application.status == "submitted",
            Application.submitted_at <= two_weeks_ago,
        )
    )).scalar_one()

    return {
        "packets_waiting_confirmation": waiting,
        "deadlines_within_48h": closing_soon,
        "stale_submitted_over_2w": stale,
    }
