from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, TimestampMixin


class EligibilityResult(Base, PKMixin, TimestampMixin):
    __tablename__ = "eligibility_results"
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    jd_evidence: Mapped[list] = mapped_column(JSON, default=list)
    context_evidence: Mapped[list] = mapped_column(JSON, default=list)
    conflicts: Mapped[list] = mapped_column(JSON, default=list)
    unknowns: Mapped[list] = mapped_column(JSON, default=list)
    needs_user_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)


class RankingProfile(Base, PKMixin, TimestampMixin):
    __tablename__ = "ranking_profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="default")
    active_version_id: Mapped[str | None] = mapped_column(String(32))


class RankingVersion(Base, PKMixin, TimestampMixin):
    __tablename__ = "ranking_versions"
    profile_id: Mapped[str] = mapped_column(ForeignKey("ranking_profiles.id"), index=True)
    version_label: Mapped[str] = mapped_column(String(40), nullable=False)
    weights: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
    created_reason: Mapped[str | None] = mapped_column(String(255))


class JobMatch(Base, PKMixin, TimestampMixin):
    __tablename__ = "job_matches"
    __table_args__ = (UniqueConstraint("job_id", "ranking_version_id", name="uq_match"),)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    ranking_version_id: Mapped[str] = mapped_column(ForeignKey("ranking_versions.id"))
    total_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    strategy: Mapped[str] = mapped_column(String(20), default="manual")  # quick/serious/manual
    why_recommended: Mapped[list] = mapped_column(JSON, default=list)
    why_not: Mapped[list] = mapped_column(JSON, default=list)
    suggested_minutes: Mapped[int] = mapped_column(Float, default=0)


class MatchDimension(Base, PKMixin, TimestampMixin):
    __tablename__ = "match_dimensions"
    match_id: Mapped[str] = mapped_column(ForeignKey("job_matches.id"), index=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    weight: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    uncertainty: Mapped[str | None] = mapped_column(Text)


class MatchEvidence(Base, PKMixin, TimestampMixin):
    __tablename__ = "match_evidence"
    dimension_id: Mapped[str] = mapped_column(ForeignKey("match_dimensions.id"), index=True)
    polarity: Mapped[str] = mapped_column(String(10))  # positive/negative
    text: Mapped[str] = mapped_column(Text)
    origin: Mapped[str | None] = mapped_column(String(40))  # jd/context
