from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_token
from app.db.session import get_session
from app.models.ammo import AmmoBlock
from app.models.ops import AuditLog

router = APIRouter(prefix="/ammo", tags=["ammo"], dependencies=[Depends(require_token)])

CATEGORIES = [
    "resume_bullet",     # 简历 bullet
    "project",           # 项目描述
    "skill_combo",       # 技能组合
    "story",             # 面试故事 / STAR
    "answer_template",   # 标准问答模板
    "cover_paragraph",   # cover letter 段落
    "headline",          # 一句话定位
    "other",
]


class AmmoIn(BaseModel):
    category: str
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)
    direction: str | None = None
    variant_of: str | None = None
    contains_metrics: bool = False
    notes: str | None = None
    source: str = "user_confirmed"


async def _sole_user_id(session: AsyncSession) -> str:
    from app.models.user import User

    uid = (await session.execute(select(User.id).limit(1))).scalar_one_or_none()
    if not uid:
        raise HTTPException(400, "no user exists yet")
    return uid


def _dto(b: AmmoBlock) -> dict:
    return {
        "id": b.id,
        "category": b.category,
        "title": b.title,
        "content": b.content,
        "tags": b.tags,
        "direction": b.direction,
        "variant_of": b.variant_of,
        "is_master": b.variant_of is None,
        "contains_metrics": b.contains_metrics,
        "usage_count": b.usage_count,
        "last_used_at": b.last_used_at,
        "provenance": b.source,
        "user_confirmed": b.user_confirmed,
        "notes": b.notes,
    }


@router.get("/categories")
async def categories() -> dict:
    return {"categories": CATEGORIES}


@router.get("")
async def list_ammo(
    category: str | None = Query(None),
    direction: str | None = Query(None),
    tag: str | None = Query(None),
    q: str | None = Query(None, description="substring search in title/content"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Browse the 弹药库. Grouped so 母本 and its 变体 stay together."""
    stmt = select(AmmoBlock).where(AmmoBlock.deleted_at.is_(None))
    if category:
        stmt = stmt.where(AmmoBlock.category == category)
    if direction:
        stmt = stmt.where(AmmoBlock.direction == direction)
    blocks = (await session.execute(stmt)).scalars().all()

    if tag:
        blocks = [b for b in blocks if tag in (b.tags or [])]
    if q:
        ql = q.lower()
        blocks = [b for b in blocks if ql in b.title.lower() or ql in b.content.lower()]

    by_id = {b.id: b for b in blocks}
    groups: list[dict] = []
    for b in blocks:
        if b.variant_of is None:
            variants = [_dto(v) for v in blocks if v.variant_of == b.id]
            groups.append({**_dto(b), "variants": variants})
    # Variants whose master was filtered out still surface on their own.
    orphans = [
        _dto(b) for b in blocks if b.variant_of is not None and b.variant_of not in by_id
    ]
    return {"count": len(blocks), "groups": groups, "orphan_variants": orphans}


@router.post("")
async def create_ammo(
    payload: AmmoIn, session: AsyncSession = Depends(get_session)
) -> dict:
    if payload.category not in CATEGORIES:
        raise HTTPException(400, f"category must be one of {CATEGORIES}")
    user_id = await _sole_user_id(session)
    block = AmmoBlock(
        user_id=user_id,
        category=payload.category,
        title=payload.title,
        content=payload.content,
        tags=payload.tags,
        direction=payload.direction,
        variant_of=payload.variant_of,
        contains_metrics=payload.contains_metrics,
        notes=payload.notes,
        source=payload.source,
        user_confirmed=(payload.source == "user_confirmed"),
    )
    session.add(block)
    session.add(AuditLog(actor="user", action="ammo_create", entity_type="ammo_block",
                         entity_id=block.id, summary=payload.title))
    await session.commit()
    return _dto(block)


@router.patch("/{block_id}")
async def update_ammo(
    block_id: str, payload: dict = Body(...), session: AsyncSession = Depends(get_session)
) -> dict:
    block = await session.get(AmmoBlock, block_id)
    if not block or block.deleted_at:
        raise HTTPException(404, "ammo block not found")
    for field in ("title", "content", "tags", "direction", "category",
                  "contains_metrics", "notes"):
        if field in payload:
            setattr(block, field, payload[field])
    block.version += 1
    await session.commit()
    return _dto(block)


@router.delete("/{block_id}")
async def delete_ammo(
    block_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    block = await session.get(AmmoBlock, block_id)
    if not block or block.deleted_at:
        raise HTTPException(404, "ammo block not found")
    block.deleted_at = datetime.now(UTC)  # soft delete — recoverable
    await session.commit()
    return {"id": block_id, "deleted": True}


@router.post("/{block_id}/used")
async def mark_used(
    block_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """Bump usage telemetry so the library can surface what actually gets used."""
    block = await session.get(AmmoBlock, block_id)
    if not block or block.deleted_at:
        raise HTTPException(404, "ammo block not found")
    block.usage_count += 1
    block.last_used_at = datetime.now(UTC)
    await session.commit()
    return {"id": block_id, "usage_count": block.usage_count}
