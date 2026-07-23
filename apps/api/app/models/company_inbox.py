from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, TimestampMixin

# Persistence for the company-tier-centric inbox. Recommendations are computed
# server-side and stored with their inputs, so a recommendation can always be
# explained and reproduced later — never recomputed ad hoc in the browser.


class CompanyWatchlist(Base, PKMixin, TimestampMixin):
    """Companies the user is actively monitoring."""

    __tablename__ = "company_watchlists"
    __table_args__ = (UniqueConstraint("user_id", "company_id", name="uq_watch"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    priority_note: Mapped[str | None] = mapped_column(Text)
    muted: Mapped[bool] = mapped_column(Boolean, default=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CompanyApplicationPolicy(Base, PKMixin, TimestampMixin):
    """Per-company application limit. A default, not a hard rule.

    The user may raise it deliberately when a company genuinely has separate
    teams; the override and its reason are recorded.
    """

    __tablename__ = "company_application_policies"
    __table_args__ = (UniqueConstraint("user_id", "company_id", name="uq_policy"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    recommended_limit: Mapped[int] = mapped_column(Integer, default=3)
    user_override_limit: Mapped[int | None] = mapped_column(Integer)
    override_reason: Mapped[str | None] = mapped_column(Text)


class RoleSimilarityGroup(Base, PKMixin, TimestampMixin):
    """A cluster of near-duplicate requisitions at one company."""

    __tablename__ = "role_similarity_groups"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    group_key: Mapped[str] = mapped_column(String(40), index=True)
    representative_job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"))
    member_count: Mapped[int] = mapped_column(Integer, default=1)
    max_redundancy_risk: Mapped[float] = mapped_column(Float, default=0.0)
    rationale: Mapped[str | None] = mapped_column(Text)


class RecommendedApplicationSet(Base, PKMixin, TimestampMixin):
    """One computed recommendation set for a company, with its provenance."""

    __tablename__ = "recommended_application_sets"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)

    calculation_version: Mapped[str] = mapped_column(String(30), default="inbox-v1")
    ranking_mode: Mapped[str] = mapped_column(String(20), default="internship")
    company_tier: Mapped[str] = mapped_column(String(4), default="")
    company_tier_display: Mapped[str] = mapped_column(String(40), default="")
    provisional: Mapped[bool] = mapped_column(Boolean, default=False)

    recommended_limit: Mapped[int] = mapped_column(Integer, default=3)
    recommended_count: Mapped[int] = mapped_column(Integer, default=0)
    excluded_count: Mapped[int] = mapped_column(Integer, default=0)
    already_applied_count: Mapped[int] = mapped_column(Integer, default=0)
    over_limit: Mapped[bool] = mapped_column(Boolean, default=False)

    # Snapshot of the inputs the decision was made from.
    evidence_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[list] = mapped_column(JSON, default=list)

    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_override: Mapped[bool] = mapped_column(Boolean, default=False)
    override_reason: Mapped[str | None] = mapped_column(Text)


class RecommendedApplicationSetItem(Base, PKMixin, TimestampMixin):
    """One role inside a recommendation set — recommended OR excluded.

    Exclusions are stored too: the user must be able to see what was held back
    and why, not only what survived.
    """

    __tablename__ = "recommended_application_set_items"

    set_id: Mapped[str] = mapped_column(
        ForeignKey("recommended_application_sets.id"), index=True
    )
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)

    status: Mapped[str] = mapped_column(String(20), index=True)  # recommended|excluded
    rank: Mapped[int | None] = mapped_column(Integer)            # within the company
    global_rank: Mapped[int | None] = mapped_column(Integer)

    title: Mapped[str] = mapped_column(String(500), default="")
    role_family: Mapped[str] = mapped_column(String(40), default="")
    role_band: Mapped[str] = mapped_column(String(4), default="")
    similarity_group_key: Mapped[str | None] = mapped_column(String(40), index=True)
    redundancy_risk: Mapped[float] = mapped_column(Float, default=0.0)

    application_priority: Mapped[float] = mapped_column(Float, default=0.0)
    company_platform_value: Mapped[float] = mapped_column(Float, default=0.0)
    role_strategic_value: Mapped[float] = mapped_column(Float, default=0.0)
    current_candidate_fit: Mapped[float] = mapped_column(Float, default=0.0)
    team_project_quality: Mapped[float] = mapped_column(Float, default=0.0)
    career_optionality: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_coverage: Mapped[float] = mapped_column(Float, default=0.0)

    reason: Mapped[str] = mapped_column(Text, default="")
    superseded_by: Mapped[str | None] = mapped_column(String(500))
    duplicates_applied_role: Mapped[bool] = mapped_column(Boolean, default=False)
    has_official_link: Mapped[bool] = mapped_column(Boolean, default=True)


class CompanyRoleRanking(Base, PKMixin, TimestampMixin):
    """Materialised ordering so views do not recompute on every request."""

    __tablename__ = "company_role_rankings"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_role_rank"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    company_internal_rank: Mapped[int] = mapped_column(Integer, default=0)
    global_rank: Mapped[int] = mapped_column(Integer, default=0, index=True)
    application_priority: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
