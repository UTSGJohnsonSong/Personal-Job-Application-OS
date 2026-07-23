"""Locations must survive ingestion.

Connectors parsed them and `ingest_result` never wrote a JobLocation row, so
every posting in the database was location-less: 1,841 real jobs, 370 of them
Canadian, and nothing downstream could tell a Toronto co-op from a Singapore
one. Eligibility and every Canada filter were running on no data at all.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.ingestion.sync import ingest_result
from app.models.sourcing import Company, Job, JobLocation, JobSource
from app.schemas.connector import ConnectorResult, RawJob, RawLocation


def _raw(job_id: str, title: str, location: str | None) -> RawJob:
    return RawJob(
        source_job_id=job_id,
        title=title,
        company_name="Acme",
        locations=[RawLocation(raw_text=location)] if location else [],
        official_source_url=f"https://acme.example/{job_id}",
        canonical_application_url=f"https://acme.example/{job_id}",
        source_status="open",
        content_hash=f"hash-{job_id}",
    )


async def _source(session) -> JobSource:
    company = Company(name="Acme", normalized_name="acme")
    session.add(company)
    await session.flush()
    source = JobSource(connector_key="greenhouse", external_id="acme",
                       display_name="Acme", company_id=company.id, config={})
    session.add(source)
    await session.flush()
    return source


def _result(*raws: RawJob) -> ConnectorResult:
    return ConnectorResult(raw_jobs=list(raws), fetched_at=datetime.now(UTC))


@pytest.mark.anyio
async def test_locations_are_persisted(session) -> None:
    source = await _source(session)
    await ingest_result(session, source, _result(
        _raw("1", "Data Analyst Co-op", "Toronto, ON"),
        _raw("2", "Backend Engineer", "Singapore"),
    ))
    await session.flush()

    rows = (await session.execute(select(JobLocation))).scalars().all()
    assert {r.raw_text for r in rows} == {"Toronto, ON", "Singapore"}


@pytest.mark.anyio
async def test_canadian_postings_are_distinguishable(session) -> None:
    """The point of storing them: a Canada filter has to be able to work."""
    source = await _source(session)
    await ingest_result(session, source, _result(
        _raw("1", "Co-op", "Toronto, ON"),
        _raw("2", "Co-op", "Seattle, WA"),
    ))
    await session.flush()

    canadian = (await session.execute(
        select(Job).join(JobLocation, JobLocation.job_id == Job.id)
        .where(JobLocation.raw_text.like("%Toronto%"))
    )).scalars().all()
    assert len(canadian) == 1


@pytest.mark.anyio
async def test_a_moved_posting_does_not_keep_its_old_location(session) -> None:
    """The board is the authority, so locations are replaced, not merged."""
    source = await _source(session)
    await ingest_result(session, source, _result(_raw("1", "Analyst", "Toronto, ON")))
    await session.flush()

    moved = _raw("1", "Analyst", "Vancouver, BC")
    moved.content_hash = "hash-changed"
    await ingest_result(session, source, _result(moved))
    await session.flush()

    rows = (await session.execute(select(JobLocation))).scalars().all()
    assert [r.raw_text for r in rows] == ["Vancouver, BC"]


@pytest.mark.anyio
async def test_a_posting_without_a_location_stores_none(session) -> None:
    """Absent is recorded as absent — never invented, never inherited."""
    source = await _source(session)
    await ingest_result(session, source, _result(_raw("1", "Analyst", None)))
    await session.flush()

    rows = (await session.execute(select(JobLocation))).scalars().all()
    assert rows == []
