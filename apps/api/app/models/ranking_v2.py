from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, TimestampMixin

# v2 ranking persistence. Additive: legacy job_matches rows are preserved and
# stamped formula_version="legacy-v1" (see docs/RANKING_MIGRATION.md).


class CompanyEvidence(Base, PKMixin, TimestampMixin):
    """One graded fact about a company, supporting exactly one dimension."""

    __tablename__ = "company_evidence"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_type: Mapped[str] = mapped_column(String(60), nullable=False)
    grade: Mapped[str] = mapped_column(String(1), nullable=False)  # A / B / C
    supports_dimension: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text)
    value: Mapped[float | None] = mapped_column(Float)  # None => risk flag only
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    still_valid: Mapped[bool] = mapped_column(Boolean, default=True)


class CompanyScoreVersion(Base, PKMixin, TimestampMixin):
    """A computed company assessment at a point in time."""

    __tablename__ = "company_score_versions"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    formula_version: Mapped[str] = mapped_column(String(20), default="v2")
    known_evidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_coverage: Mapped[float] = mapped_column(Float, default=0.0)
    conservative_score: Mapped[float] = mapped_column(Float, default=0.0)
    system_tier: Mapped[str] = mapped_column(String(2), default="D")
    tier_status: Mapped[str] = mapped_column(String(20), default="unrated")
    dimension_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_flags: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[list] = mapped_column(JSON, default=list)
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CompanyPersonalOverride(Base, PKMixin, TimestampMixin):
    """User's manual tier, stored SEPARATELY from the evidence-derived tier.

    Creating one requires explicit user confirmation.
    """

    __tablename__ = "company_personal_overrides"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    personal_tier: Mapped[str] = mapped_column(String(2), nullable=False)
    override_reason: Mapped[str] = mapped_column(Text, nullable=False)
    user_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class CompanyResearchRun(Base, PKMixin, TimestampMixin):
    """Background company-research attempt. Failures are never silent."""

    __tablename__ = "company_research_runs"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    steps_completed: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    needs_research: Mapped[bool] = mapped_column(Boolean, default=True)


class RoleClassificationRow(Base, PKMixin, TimestampMixin):
    __tablename__ = "role_classifications"

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    role_type: Mapped[str] = mapped_column(String(60), nullable=False)
    band: Mapped[str] = mapped_column(String(2), nullable=False, index=True)  # R1..R4
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    technical_density: Mapped[float] = mapped_column(Float, default=0.0)
    transferability: Mapped[float] = mapped_column(Float, default=0.0)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    signals_positive: Mapped[list] = mapped_column(JSON, default=list)
    signals_negative: Mapped[list] = mapped_column(JSON, default=list)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    formula_version: Mapped[str] = mapped_column(String(20), default="v2")


class ApplicationPriorityScore(Base, PKMixin, TimestampMixin):
    """The v2 result. Six scores stay separate — never merged into a match %."""

    __tablename__ = "application_priority_scores"

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    ranking_mode: Mapped[str] = mapped_column(String(20), default="internship")
    formula_version: Mapped[str] = mapped_column(String(20), default="v2", index=True)
    weights_version: Mapped[str] = mapped_column(String(40), default="v2-internship-default")

    eligibility_gate: Mapped[str] = mapped_column(String(10), index=True)  # PASS/REVIEW/FAIL
    company_tier: Mapped[str] = mapped_column(String(2))
    # Display form carries qualifiers, e.g. "S?" or "C? (unrated)" — must not be
    # tight. Postgres enforces VARCHAR length; SQLite does not, so a too-small
    # column only fails in production.
    company_tier_display: Mapped[str] = mapped_column(String(40))
    role_band: Mapped[str] = mapped_column(String(2))
    role_type: Mapped[str] = mapped_column(String(60))

    company_platform_value: Mapped[float] = mapped_column(Float, default=0.0)
    role_strategic_value: Mapped[float] = mapped_column(Float, default=0.0)
    current_candidate_fit: Mapped[float] = mapped_column(Float, default=0.0)
    team_project_quality: Mapped[float] = mapped_column(Float, default=0.0)
    career_optionality: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_coverage: Mapped[float] = mapped_column(Float, default=0.0)
    application_priority: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    opportunity_estimate: Mapped[str] = mapped_column(String(120), default="")
    recommendation: Mapped[str] = mapped_column(String(60), default="")
    # Rules accumulate qualifiers ("... | priority floor 80 applied").
    interaction_rule: Mapped[str] = mapped_column(String(255), default="")
    why: Mapped[list] = mapped_column(JSON, default=list)
    why_not: Mapped[list] = mapped_column(JSON, default=list)
    unknowns: Mapped[list] = mapped_column(JSON, default=list)

    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manually_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    override_reason: Mapped[str | None] = mapped_column(Text)


class PairwisePreference(Base, PKMixin, TimestampMixin):
    """User chose job A over job B — the signal that calibrates platform vs fit."""

    __tablename__ = "pairwise_preferences"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    chosen_job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    rejected_job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    chosen_tier: Mapped[str | None] = mapped_column(String(2))
    rejected_tier: Mapped[str | None] = mapped_column(String(2))
    chosen_band: Mapped[str | None] = mapped_column(String(2))
    rejected_band: Mapped[str | None] = mapped_column(String(2))
    context: Mapped[str | None] = mapped_column(String(60))  # queue_order / skip / apply
    note: Mapped[str | None] = mapped_column(Text)


class LearningSuggestion(Base, PKMixin, TimestampMixin):
    """Proposed weight change. NEVER auto-applied — requires user approval."""

    __tablename__ = "learning_suggestions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40), default="weight_adjustment")
    explanation: Mapped[str] = mapped_column(Text)
    supporting_data: Mapped[dict] = mapped_column(JSON, default=dict)
    before_weights: Mapped[dict] = mapped_column(JSON, default=dict)
    after_weights: Mapped[dict] = mapped_column(JSON, default=dict)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/approved/rejected
    approved_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rolled_back: Mapped[bool] = mapped_column(Boolean, default=False)
