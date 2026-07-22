from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RawLocation(BaseModel):
    raw_text: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None


class RawJob(BaseModel):
    """Provenance-bearing DTO emitted by every connector.

    All text fields are treated as UNTRUSTED input downstream.
    """

    source_job_id: str
    title: str
    company_name: str | None = None
    description_text: str | None = None
    department: str | None = None
    employment_type: str | None = None
    remote_mode: str | None = None
    locations: list[RawLocation] = Field(default_factory=list)

    official_source_url: str | None = None
    canonical_application_url: str | None = None

    source_posted_at: datetime | None = None
    source_updated_at: datetime | None = None
    source_status: str = "open"

    content_hash: str | None = None
    raw: dict = Field(default_factory=dict)


class ConnectorResult(BaseModel):
    raw_jobs: list[RawJob] = Field(default_factory=list)
    etag: str | None = None
    last_modified: str | None = None
    fetched_at: datetime | None = None
    diagnostics: dict = Field(default_factory=dict)
    not_modified: bool = False


class SourceConfig(BaseModel):
    connector_key: str
    external_id: str  # board token / company slug
    display_name: str
    source_priority: int = 1
    etag: str | None = None
    last_modified: str | None = None
    config: dict = Field(default_factory=dict)
