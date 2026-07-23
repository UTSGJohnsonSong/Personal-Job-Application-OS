"""The application pool: tiers, companies, and their open roles."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_token
from app.db.session import SessionLocal, get_session
from app.services.inbox import _sole_user_id
from app.services.pool import (
    REFRESH,
    build_pool,
    company_detail,
    estimate_refresh,
    start_refresh,
)

router = APIRouter(prefix="/pool", tags=["pool"], dependencies=[Depends(require_token)])


async def _uid(session: AsyncSession) -> str:
    uid = await _sole_user_id(session)
    if not uid:
        raise HTTPException(400, "no user exists yet")
    return uid


@router.get("")
async def pool(session: AsyncSession = Depends(get_session)) -> dict:
    return await build_pool(session, await _uid(session))


@router.get("/company/{key}")
async def company(key: str, session: AsyncSession = Depends(get_session)) -> dict:
    detail = await company_detail(session, await _uid(session), key)
    if detail is None:
        raise HTTPException(404, f"no company {key!r} in the registry")
    return detail


@router.get("/refresh/estimate")
async def refresh_estimate() -> dict:
    """What the wait will cost, before committing to it."""
    return estimate_refresh()


@router.post("/refresh")
async def refresh(session: AsyncSession = Depends(get_session)) -> dict:
    """Kick off a refresh in the background and return immediately.

    Synchronous refresh would hold the request open for minutes; the UI needs
    to show progress while it runs, so the work is detached and polled.
    """
    return start_refresh(SessionLocal, await _uid(session))


@router.get("/refresh/status")
async def refresh_status() -> dict:
    return REFRESH.snapshot()
