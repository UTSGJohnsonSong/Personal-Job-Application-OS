from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, ProvenanceMixin, TimestampMixin


class ApplicationPacket(Base, PKMixin, TimestampMixin):
    __tablename__ = "application_packets"
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    resume_version_id: Mapped[str | None] = mapped_column(ForeignKey("resume_versions.id"))
    status: Mapped[str] = mapped_column(String(30), default="preparing")
    packet_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    needs_cover_letter: Mapped[bool] = mapped_column(Boolean, default=False)
    risks: Mapped[list] = mapped_column(JSON, default=list)
    uncertainties: Mapped[list] = mapped_column(JSON, default=list)


class GeneratedDocument(Base, PKMixin, TimestampMixin, ProvenanceMixin):
    __tablename__ = "generated_documents"
    packet_id: Mapped[str] = mapped_column(ForeignKey("application_packets.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))  # cover_letter/summary/open_ended
    content: Mapped[str | None] = mapped_column(Text)
    model_run_id: Mapped[str | None] = mapped_column(String(32))
    user_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class ApplicationAnswer(Base, PKMixin, TimestampMixin, ProvenanceMixin):
    __tablename__ = "application_answers"
    packet_id: Mapped[str] = mapped_column(ForeignKey("application_packets.id"), index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    field_type: Mapped[str | None] = mapped_column(String(40))
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_user_input: Mapped[bool] = mapped_column(Boolean, default=False)
    answer_source: Mapped[str | None] = mapped_column(String(255))  # which context item


class Application(Base, PKMixin, TimestampMixin):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_application"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    packet_id: Mapped[str | None] = mapped_column(ForeignKey("application_packets.id"))
    status: Mapped[str] = mapped_column(String(30), default="discovered", index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- Apply queue ("想投列表") ---
    # queued_at set => the user has put this job in the queue to apply to.
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    queue_note: Mapped[str | None] = mapped_column(Text)
    # Manual override of ranking order within the queue (lower = sooner).
    queue_priority: Mapped[int | None] = mapped_column()


class ApplicationEvent(Base, PKMixin, TimestampMixin):
    __tablename__ = "application_events"
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str | None] = mapped_column(String(30))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ApplicationConfirmation(Base, PKMixin, TimestampMixin):
    """Immutable per-job pre-submit confirmation. Binds the exact packet.

    A job may not reach `submitted` unless a row here has confirmed_at set and
    packet_hash matching the submitted packet. See docs/APPLICATION_AUTOMATION.md.
    """

    __tablename__ = "application_confirmations"
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)
    packet_id: Mapped[str] = mapped_column(ForeignKey("application_packets.id"))
    packet_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_answers_hash: Mapped[str | None] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)  # what the user saw
