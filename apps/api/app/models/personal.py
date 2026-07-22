from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.provenance import SensitivityLevel
from app.db.base import Base, PKMixin, ProvenanceMixin, SoftDeleteMixin, TimestampMixin


class PersonalContextItem(Base, PKMixin, TimestampMixin, ProvenanceMixin, SoftDeleteMixin):
    """Generic provenance-bearing fact about the user. See docs/PERSONAL_CONTEXT.md."""

    __tablename__ = "personal_context_items"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    can_use_for_application: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sensitivity_level: Mapped[str] = mapped_column(
        String(20), default=SensitivityLevel.LOW.value, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CandidateProfile(Base, PKMixin, TimestampMixin, ProvenanceMixin):
    __tablename__ = "candidate_profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    headline: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(255))
    links: Mapped[dict] = mapped_column(JSON, default=dict)


class CandidateExperience(Base, PKMixin, TimestampMixin, ProvenanceMixin):
    __tablename__ = "candidate_experiences"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    company: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(255))
    start_date: Mapped[str | None] = mapped_column(String(20))
    end_date: Mapped[str | None] = mapped_column(String(20))
    bullets: Mapped[list] = mapped_column(JSON, default=list)


class CandidateProject(Base, PKMixin, TimestampMixin, ProvenanceMixin):
    __tablename__ = "candidate_projects"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    tech: Mapped[list] = mapped_column(JSON, default=list)
    url: Mapped[str | None] = mapped_column(String(500))


class CandidateEducation(Base, PKMixin, TimestampMixin, ProvenanceMixin):
    __tablename__ = "candidate_education"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    school: Mapped[str | None] = mapped_column(String(255))
    degree: Mapped[str | None] = mapped_column(String(120))
    field: Mapped[str | None] = mapped_column(String(120))
    start_date: Mapped[str | None] = mapped_column(String(20))
    end_date: Mapped[str | None] = mapped_column(String(20))
    gpa: Mapped[str | None] = mapped_column(String(20))  # sensitive_legal


class CandidateSkill(Base, PKMixin, TimestampMixin, ProvenanceMixin):
    __tablename__ = "candidate_skills"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    proficiency: Mapped[str | None] = mapped_column(String(40))  # exact wording preserved
    years: Mapped[float | None] = mapped_column(Float)


class WorkAuthorization(Base, PKMixin, TimestampMixin, ProvenanceMixin):
    __tablename__ = "work_authorizations"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False)  # ISO-2
    status: Mapped[str | None] = mapped_column(String(120))  # e.g. citizen/pr/visa-x
    needs_sponsorship: Mapped[bool | None] = mapped_column(Boolean)
    sensitivity_level: Mapped[str] = mapped_column(String(20), default="sensitive_legal")


class ApplicationPreference(Base, PKMixin, TimestampMixin, ProvenanceMixin):
    __tablename__ = "application_preferences"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    locations: Mapped[list] = mapped_column(JSON, default=list)
    remote_pref: Mapped[str | None] = mapped_column(String(20))  # remote/hybrid/onsite/any
    min_salary: Mapped[float | None] = mapped_column(Float)
    salary_currency: Mapped[str | None] = mapped_column(String(8))
    company_sizes: Mapped[list] = mapped_column(JSON, default=list)
    industries: Mapped[list] = mapped_column(JSON, default=list)
    target_roles: Mapped[list] = mapped_column(JSON, default=list)
    dealbreakers: Mapped[list] = mapped_column(JSON, default=list)
    weight_overrides: Mapped[dict] = mapped_column(JSON, default=dict)


class StandardAnswer(Base, PKMixin, TimestampMixin, ProvenanceMixin):
    __tablename__ = "standard_answers"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    question_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    answer: Mapped[str | None] = mapped_column(Text)
    can_use_for_application: Mapped[bool] = mapped_column(Boolean, default=False)
    sensitivity_level: Mapped[str] = mapped_column(String(20), default="low")
