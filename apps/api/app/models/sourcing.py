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

from app.core.provenance import SourcePriority
from app.db.base import Base, PKMixin, SoftDeleteMixin, TimestampMixin


class Company(Base, PKMixin, TimestampMixin):
    __tablename__ = "companies"
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    website: Mapped[str | None] = mapped_column(String(500))
    size: Mapped[str | None] = mapped_column(String(40))
    industry: Mapped[str | None] = mapped_column(String(120))


class CompanyDomain(Base, PKMixin, TimestampMixin):
    __tablename__ = "company_domains"
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)


class CompanyAlias(Base, PKMixin, TimestampMixin):
    __tablename__ = "company_aliases"
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    alias: Mapped[str] = mapped_column(String(255), nullable=False, index=True)


class CompanyCareerPage(Base, PKMixin, TimestampMixin):
    __tablename__ = "company_career_pages"
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    ats_type: Mapped[str | None] = mapped_column(String(40))  # greenhouse/lever/ashby/...


class JobSource(Base, PKMixin, TimestampMixin):
    """A configured source instance, e.g. Greenhouse board 'acme'."""

    __tablename__ = "job_sources"
    __table_args__ = (UniqueConstraint("connector_key", "external_id", name="uq_source"),)

    connector_key: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)  # board token
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"))
    source_priority: Mapped[int] = mapped_column(
        Integer, default=SourcePriority.FIRST_PARTY_ATS.value
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    # freshness / politeness bookkeeping
    etag: Mapped[str | None] = mapped_column(String(255))
    last_modified: Mapped[str | None] = mapped_column(String(255))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    health: Mapped[str] = mapped_column(String(20), default="unknown")


class SourceSyncRun(Base, PKMixin, TimestampMixin):
    __tablename__ = "source_sync_runs"
    source_id: Mapped[str] = mapped_column(ForeignKey("job_sources.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running/ok/failed
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    jobs_seen: Mapped[int] = mapped_column(Integer, default=0)
    jobs_new: Mapped[int] = mapped_column(Integer, default=0)
    jobs_updated: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class Job(Base, PKMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source_id", "source_job_id", name="uq_source_job"),
    )

    source_id: Mapped[str] = mapped_column(ForeignKey("job_sources.id"), index=True)
    source_job_id: Mapped[str] = mapped_column(String(255), nullable=False)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"), index=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(500), index=True)
    description_text: Mapped[str | None] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(String(255))
    employment_type: Mapped[str | None] = mapped_column(String(60))
    remote_mode: Mapped[str | None] = mapped_column(String(20))  # remote/hybrid/onsite

    official_source_url: Mapped[str | None] = mapped_column(String(1000))
    canonical_application_url: Mapped[str | None] = mapped_column(String(1000), index=True)

    # freshness (see docs/FRESHNESS_STRATEGY.md)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    application_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_status: Mapped[str] = mapped_column(String(20), default="open")
    current_status: Mapped[str] = mapped_column(String(30), default="discovered", index=True)
    source_priority: Mapped[int] = mapped_column(Integer, default=1)
    freshness_score: Mapped[float] = mapped_column(Float, default=1.0)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)

    inbox_category: Mapped[str] = mapped_column(String(20), default="new", index=True)
    duplicate_group_id: Mapped[str | None] = mapped_column(String(32), index=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)


class JobSnapshot(Base, PKMixin, TimestampMixin):
    __tablename__ = "job_snapshots"
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_status: Mapped[str] = mapped_column(String(20))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict] = mapped_column(JSON, default=dict)


class JobRequirement(Base, PKMixin, TimestampMixin):
    """Structured, evidence-bearing extraction from the JD."""

    __tablename__ = "job_requirements"
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    field: Mapped[str] = mapped_column(String(80), nullable=False)  # e.g. degree/skill/auth
    value: Mapped[str | None] = mapped_column(Text)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    evidence: Mapped[str | None] = mapped_column(Text)  # verbatim JD span
    confidence: Mapped[float] = mapped_column(Float, default=0.5)


class JobLocation(Base, PKMixin, TimestampMixin):
    __tablename__ = "job_locations"
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    raw_text: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(120))
    region: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(2))


class JobEmbedding(Base, PKMixin, TimestampMixin):
    """Embedding stored as JSON for portability; prod adds a pgvector column."""

    __tablename__ = "job_embeddings"
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), unique=True, index=True)
    model: Mapped[str] = mapped_column(String(80))
    vector: Mapped[list] = mapped_column(JSON, default=list)


class DuplicateGroup(Base, PKMixin, TimestampMixin):
    __tablename__ = "duplicate_groups"
    canonical_job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"))
    reason: Mapped[str | None] = mapped_column(String(120))
    member_count: Mapped[int] = mapped_column(Integer, default=1)
