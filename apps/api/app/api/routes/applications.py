from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_token
from app.applications.state_machine import (
    AppStatus,
    IllegalTransition,
    SubmissionNotConfirmed,
    assert_transition,
    guard_submit,
)
from app.db.session import get_session
from app.models.application import (
    Application,
    ApplicationConfirmation,
    ApplicationEvent,
    ApplicationPacket,
)
from app.models.ops import AuditLog

router = APIRouter(
    prefix="/applications", tags=["applications"], dependencies=[Depends(require_token)]
)


async def _record_event(session, app: Application, frm, to, event_type, detail=None):
    session.add(
        ApplicationEvent(
            application_id=app.id,
            event_type=event_type,
            from_status=frm,
            to_status=to,
            detail=detail or {},
            occurred_at=datetime.now(UTC),
        )
    )


@router.get("/{app_id}")
async def get_application(app_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    app = await session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "application not found")
    return {
        "id": app.id,
        "job_id": app.job_id,
        "status": app.status,
        "packet_id": app.packet_id,
        "submitted_at": app.submitted_at,
    }


@router.post("/{app_id}/prepare-confirmation")
async def prepare_confirmation(
    app_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """Build the review snapshot and move to waiting_for_confirmation (Level 3).

    Creates an UNCONFIRMED confirmation record bound to the exact packet hash.
    """
    app = await session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "application not found")
    if not app.packet_id:
        raise HTTPException(400, "application has no packet to confirm")
    packet = await session.get(ApplicationPacket, app.packet_id)
    if not packet or not packet.packet_hash:
        raise HTTPException(400, "packet not finalized")

    try:
        assert_transition(AppStatus(app.status), AppStatus.WAITING_FOR_CONFIRMATION)
    except IllegalTransition as exc:
        raise HTTPException(409, str(exc)) from exc

    frm = app.status
    app.status = AppStatus.WAITING_FOR_CONFIRMATION.value
    app.last_status_change_at = datetime.now(UTC)
    confirmation = ApplicationConfirmation(
        application_id=app.id,
        packet_id=packet.id,
        packet_hash=packet.packet_hash,
        confirmed_at=None,
        confirmed_by_user=False,
    )
    session.add(confirmation)
    await _record_event(session, app, frm, app.status, "prepare_confirmation")
    session.add(AuditLog(actor="user", action="prepare_confirmation",
                         entity_type="application", entity_id=app.id))
    await session.commit()
    return {
        "application_id": app.id,
        "status": app.status,
        "packet_hash": packet.packet_hash,
        "review_required": True,
        "message": "Review every field, then POST /confirm-and-submit with this packet_hash.",
    }


@router.post("/{app_id}/confirm-and-submit")
async def confirm_and_submit(
    app_id: str,
    packet_hash_ack: str = Body(..., embed=True),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """The ONLY path to `submitted`. Requires the user to echo the exact packet hash.

    Hard invariant (docs/APPLICATION_AUTOMATION.md): no confirmation, no submit;
    a confirmation for one job/packet never applies to another.
    """
    app = await session.get(Application, app_id)
    if not app:
        raise HTTPException(404, "application not found")

    confirmation = (
        await session.execute(
            select(ApplicationConfirmation)
            .where(ApplicationConfirmation.application_id == app.id)
            .order_by(ApplicationConfirmation.created_at.desc())
        )
    ).scalars().first()
    if not confirmation:
        raise HTTPException(409, "no confirmation prepared for this application")

    # Mark the explicit human confirmation.
    confirmation.confirmed_at = datetime.now(UTC)
    confirmation.confirmed_by_user = True

    try:
        guard_submit(
            AppStatus(app.status),
            confirmation_present=True,
            confirmed_by_user=confirmation.confirmed_by_user,
            confirmation_packet_hash=confirmation.packet_hash,
            submitted_packet_hash=packet_hash_ack,
        )
    except (IllegalTransition, SubmissionNotConfirmed) as exc:
        raise HTTPException(409, str(exc)) from exc

    frm = app.status
    app.status = AppStatus.SUBMITTED.value
    app.submitted_at = datetime.now(UTC)
    app.last_status_change_at = app.submitted_at
    await _record_event(session, app, frm, app.status, "submitted",
                        {"packet_hash": confirmation.packet_hash})
    session.add(AuditLog(actor="user", action="submit",
                         entity_type="application", entity_id=app.id,
                         summary="confirmed and submitted",
                         meta={"packet_hash": confirmation.packet_hash}))
    await session.commit()
    return {"application_id": app.id, "status": app.status, "submitted_at": app.submitted_at}
