from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, ProvenanceMixin, SoftDeleteMixin, TimestampMixin


class ResumeVersion(Base, PKMixin, TimestampMixin, ProvenanceMixin, SoftDeleteMixin):
    __tablename__ = "resume_versions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    direction: Mapped[str | None] = mapped_column(String(80))  # e.g. "backend", "data"
    is_base: Mapped[bool] = mapped_column(Boolean, default=False)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"))


class ResumeSection(Base, PKMixin, TimestampMixin):
    __tablename__ = "resume_sections"
    resume_version_id: Mapped[str] = mapped_column(
        ForeignKey("resume_versions.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)  # summary/experience/...
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str | None] = mapped_column(String(255))


class ResumeBullet(Base, PKMixin, TimestampMixin, ProvenanceMixin):
    __tablename__ = "resume_bullets"
    section_id: Mapped[str] = mapped_column(
        ForeignKey("resume_sections.id"), nullable=False, index=True
    )
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    tailored_text: Mapped[str | None] = mapped_column(Text)
    tailoring_rationale: Mapped[str | None] = mapped_column(Text)
    changes_factual_meaning: Mapped[bool] = mapped_column(Boolean, default=False)


class Document(Base, PKMixin, TimestampMixin, ProvenanceMixin, SoftDeleteMixin):
    """Metadata for a file in private object storage. Bytes never touch the DB."""

    __tablename__ = "documents"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)  # resume/transcript/cover/...
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)  # S3 key
    content_hash: Mapped[str | None] = mapped_column(String(64))
    sensitivity_level: Mapped[str] = mapped_column(String(20), default="pii")
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
