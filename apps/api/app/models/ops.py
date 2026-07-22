from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, TimestampMixin, utcnow


class EmailConnection(Base, PKMixin, TimestampMixin):
    __tablename__ = "email_connections"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20))  # gmail/outlook
    status: Mapped[str] = mapped_column(String(20), default="disconnected")
    # Tokens are NOT stored here in plaintext; reference a secret manager key.
    secret_ref: Mapped[str | None] = mapped_column(String(255))


class EmailEvent(Base, PKMixin, TimestampMixin):
    __tablename__ = "email_events"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    application_id: Mapped[str | None] = mapped_column(ForeignKey("applications.id"))
    kind: Mapped[str] = mapped_column(String(40))  # rejection/interview/assessment/...
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    message_ref: Mapped[str | None] = mapped_column(String(255))  # provider message id
    needs_user_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    redacted_summary: Mapped[str | None] = mapped_column(Text)


class UserFeedback(Base, PKMixin, TimestampMixin):
    __tablename__ = "user_feedback"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"))
    kind: Mapped[str] = mapped_column(String(40))  # saved/skipped/score_edit/wording_edit/...
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class LearningUpdate(Base, PKMixin, TimestampMixin):
    __tablename__ = "learning_updates"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))  # weight_suggestion/calibration
    explanation: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    rolled_back: Mapped[bool] = mapped_column(Boolean, default=False)


class ModelRun(Base, PKMixin, TimestampMixin):
    __tablename__ = "model_runs"
    purpose: Mapped[str] = mapped_column(String(80))  # jd_parse/cover_letter/...
    provider: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(80))
    data_scope: Mapped[str | None] = mapped_column(String(255))  # what fields were sent
    pii_minimized: Mapped[bool] = mapped_column(Boolean, default=True)
    input_hash: Mapped[str | None] = mapped_column(String(64))
    ok: Mapped[bool] = mapped_column(Boolean, default=True)


class ConnectorFailure(Base, PKMixin, TimestampMixin):
    __tablename__ = "connector_failures"
    source_id: Mapped[str | None] = mapped_column(ForeignKey("job_sources.id"), index=True)
    connector_key: Mapped[str] = mapped_column(String(40))
    stage: Mapped[str] = mapped_column(String(40))  # fetch/parse/normalize
    error: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class Notification(Base, PKMixin, TimestampMixin):
    __tablename__ = "notifications"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)
    action_url: Mapped[str | None] = mapped_column(String(500))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base, PKMixin):
    """Append-only. No UPDATE/DELETE granted to the app DB role in production."""

    __tablename__ = "audit_logs"
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(20))  # user/system/connector/extension/worker
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(32))
    summary: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # PII-redacted
    model_run_id: Mapped[str | None] = mapped_column(String(32))
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    entry_hash: Mapped[str | None] = mapped_column(String(64))
