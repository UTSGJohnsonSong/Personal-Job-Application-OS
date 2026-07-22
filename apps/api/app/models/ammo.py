from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, ProvenanceMixin, SoftDeleteMixin, TimestampMixin


class AmmoBlock(Base, PKMixin, TimestampMixin, ProvenanceMixin, SoftDeleteMixin):
    """A reusable, categorized piece of application material ("弹药").

    Mirrors the Obsidian 弹药库 model: one 母本 (variant_of is NULL) plus any
    number of 变体 (variant_of -> the 母本). Everything carries provenance, so a
    block that was never user-confirmed can be surfaced as a draft but is not
    treated as an established fact.
    """

    __tablename__ = "ammo_blocks"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    # resume_bullet | project | skill_combo | story | answer_template |
    # cover_paragraph | headline | other
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    tags: Mapped[list] = mapped_column(JSON, default=list)
    # Which direction/target this variant is tuned for, e.g. "data-engineering".
    direction: Mapped[str | None] = mapped_column(String(80), index=True)

    # 母本/变体: NULL => this IS a 母本.
    variant_of: Mapped[str | None] = mapped_column(ForeignKey("ammo_blocks.id"), index=True)

    # Usage telemetry, so the library can surface what actually gets used.
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Factual claims must be verifiable; blocks with numbers/impact get flagged.
    contains_metrics: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
