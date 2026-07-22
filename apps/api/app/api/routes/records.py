from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_token
from app.applications.packet import build_packet_snapshot, packet_hash
from app.applications.state_machine import AppStatus
from app.db.session import get_session
from app.models.application import (
    Application,
    ApplicationAnswer,
    ApplicationEvent,
    ApplicationPacket,
    GeneratedDocument,
)
from app.models.ops import AuditLog
from app.models.resume import ResumeVersion
from app.models.sourcing import Job

router = APIRouter(prefix="/records", tags=["records"], dependencies=[Depends(require_token)])


class AnswerIn(BaseModel):
    question: str
    answer: str | None = None
    field_type: str | None = None
    is_sensitive: bool = False
    needs_user_input: bool = False
    answer_source: str | None = None  # which personal-context item it came from
    source: str = "user_confirmed"  # provenance


class RecordIn(BaseModel):
    """What the agent (or the user) writes after working an application."""

    resume_version_id: str | None = None
    resume_version_name: str | None = None  # convenience: resolve by name
    cover_letter: str | None = None
    answers: list[AnswerIn] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)
    notes: str | None = None
    risks: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


async def _get_application(session: AsyncSession, application_id: str) -> Application:
    app_row = await session.get(Application, application_id)
    if not app_row:
        raise HTTPException(404, "application not found")
    return app_row


@router.put("/{application_id}")
async def upsert_record(
    application_id: str,
    payload: RecordIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Record exactly what was used for this application.

    Every question + answer + the resume version is persisted so the user can
    expand it later and see precisely what they said to whom. Re-running this
    replaces the answer set and recomputes the packet hash (which invalidates
    any prior submit confirmation on purpose).
    """
    app_row = await _get_application(session, application_id)
    job = await session.get(Job, app_row.job_id)

    resume_version_id = payload.resume_version_id
    if not resume_version_id and payload.resume_version_name:
        resume_version_id = (
            await session.execute(
                select(ResumeVersion.id).where(
                    ResumeVersion.user_id == app_row.user_id,
                    ResumeVersion.name == payload.resume_version_name,
                )
            )
        ).scalar_one_or_none()

    packet = None
    if app_row.packet_id:
        packet = await session.get(ApplicationPacket, app_row.packet_id)
    if packet is None:
        packet = ApplicationPacket(
            job_id=app_row.job_id, user_id=app_row.user_id, status="preparing"
        )
        session.add(packet)
        await session.flush()
        app_row.packet_id = packet.id

    packet.resume_version_id = resume_version_id
    packet.risks = payload.risks
    packet.uncertainties = payload.uncertainties
    packet.needs_cover_letter = bool(payload.cover_letter)

    # Replace the answer set.
    existing = (
        await session.execute(
            select(ApplicationAnswer).where(ApplicationAnswer.packet_id == packet.id)
        )
    ).scalars().all()
    for row in existing:
        await session.delete(row)
    await session.flush()

    for a in payload.answers:
        session.add(
            ApplicationAnswer(
                packet_id=packet.id,
                question=a.question,
                answer=a.answer,
                field_type=a.field_type,
                is_sensitive=a.is_sensitive,
                needs_user_input=a.needs_user_input,
                answer_source=a.answer_source,
                source=a.source,
                user_confirmed=(a.source == "user_confirmed"),
            )
        )

    if payload.cover_letter:
        session.add(
            GeneratedDocument(
                packet_id=packet.id, kind="cover_letter",
                content=payload.cover_letter, source="generated_draft",
            )
        )

    snapshot = build_packet_snapshot(
        company=(job.title if job else ""),
        role=(job.title if job else ""),
        official_url=(job.canonical_application_url if job else None),
        resume_version_id=resume_version_id,
        answers=[{"question": a.question, "answer": a.answer} for a in payload.answers],
        documents=payload.documents,
        cover_letter=payload.cover_letter,
    )
    packet.packet_hash = packet_hash(snapshot)

    session.add(
        AuditLog(
            actor="user", action="record_application",
            entity_type="application", entity_id=app_row.id,
            summary=f"{len(payload.answers)} answers recorded",
            meta={"resume_version_id": resume_version_id, "packet_hash": packet.packet_hash},
        )
    )
    await session.commit()
    return {
        "application_id": app_row.id,
        "packet_id": packet.id,
        "packet_hash": packet.packet_hash,
        "answers_recorded": len(payload.answers),
    }


@router.get("/{application_id}")
async def get_record(
    application_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """Full expandable record: job, status, resume version, every Q&A, timeline."""
    app_row = await _get_application(session, application_id)
    job = await session.get(Job, app_row.job_id)

    answers: list[dict] = []
    resume = None
    cover = None
    packet = None
    if app_row.packet_id:
        packet = await session.get(ApplicationPacket, app_row.packet_id)
        if packet:
            rows = (
                await session.execute(
                    select(ApplicationAnswer).where(ApplicationAnswer.packet_id == packet.id)
                )
            ).scalars().all()
            answers = [
                {
                    "question": r.question,
                    "answer": r.answer,
                    "field_type": r.field_type,
                    "is_sensitive": r.is_sensitive,
                    "needs_user_input": r.needs_user_input,
                    "answer_source": r.answer_source,
                    "provenance": r.source,
                    "user_confirmed": r.user_confirmed,
                }
                for r in rows
            ]
            if packet.resume_version_id:
                rv = await session.get(ResumeVersion, packet.resume_version_id)
                if rv:
                    resume = {"id": rv.id, "name": rv.name, "direction": rv.direction}
            doc = (
                await session.execute(
                    select(GeneratedDocument).where(
                        GeneratedDocument.packet_id == packet.id,
                        GeneratedDocument.kind == "cover_letter",
                    )
                )
            ).scalars().first()
            cover = doc.content if doc else None

    events = (
        await session.execute(
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id == app_row.id)
            .order_by(ApplicationEvent.occurred_at)
        )
    ).scalars().all()

    return {
        "application_id": app_row.id,
        "status": app_row.status,
        "submitted_at": app_row.submitted_at,
        "queued_at": app_row.queued_at,
        "job": {
            "id": job.id if job else None,
            "title": job.title if job else None,
            "apply_url": job.canonical_application_url if job else None,
            "source_status": job.source_status if job else None,
        },
        "resume_version": resume,
        "cover_letter": cover,
        "answers": answers,
        "packet_hash": packet.packet_hash if packet else None,
        "risks": packet.risks if packet else [],
        "uncertainties": packet.uncertainties if packet else [],
        "timeline": [
            {
                "at": e.occurred_at,
                "event": e.event_type,
                "from": e.from_status,
                "to": e.to_status,
                "detail": e.detail,
            }
            for e in events
        ],
    }


@router.get("")
async def list_records(
    status: str | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """All application records — the 投递记录 list."""
    stmt = select(Application, Job).join(Job, Job.id == Application.job_id)
    if status:
        stmt = stmt.where(Application.status == status)
    stmt = stmt.order_by(Application.updated_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).all()
    return {
        "count": len(rows),
        "items": [
            {
                "application_id": a.id,
                "job_id": j.id,
                "title": j.title,
                "status": a.status,
                "queued": a.queued_at is not None,
                "submitted_at": a.submitted_at,
                "apply_url": j.canonical_application_url,
            }
            for a, j in rows
        ],
    }


@router.post("/{application_id}/status")
async def set_status(
    application_id: str,
    status: str = Body(..., embed=True),
    note: str | None = Body(default=None, embed=True),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Manual status switch — what the user flips on the site (interview, reject…).

    Deliberately NOT allowed to set `submitted`: reaching submitted requires the
    per-job confirmation flow (see /applications/{id}/confirm-and-submit).
    """
    app_row = await _get_application(session, application_id)
    try:
        target = AppStatus(status)
    except ValueError as exc:
        raise HTTPException(400, f"unknown status: {status}") from exc

    if target is AppStatus.SUBMITTED:
        raise HTTPException(
            409,
            "submitted must go through the per-job confirmation flow, not a manual switch",
        )

    frm = app_row.status
    app_row.status = target.value
    app_row.last_status_change_at = datetime.now(UTC)
    session.add(
        ApplicationEvent(
            application_id=app_row.id, event_type="manual_status_change",
            from_status=frm, to_status=target.value,
            detail={"note": note} if note else {}, occurred_at=datetime.now(UTC),
        )
    )
    session.add(
        AuditLog(actor="user", action="status_change", entity_type="application",
                 entity_id=app_row.id, summary=f"{frm} -> {target.value}")
    )
    await session.commit()
    return {"application_id": app_row.id, "from": frm, "to": target.value}
