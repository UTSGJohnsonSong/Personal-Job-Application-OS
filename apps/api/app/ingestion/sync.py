from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.ingestion.freshness import compute_freshness
from app.ingestion.normalize import infer_remote_mode, normalize_title
from app.models.ops import ConnectorFailure
from app.models.sourcing import Job, JobLocation, JobSnapshot, JobSource
from app.schemas.connector import ConnectorResult, RawJob

log = get_logger("ingestion.sync")


async def _find_existing(session: AsyncSession, source_id: str, raw: RawJob) -> Job | None:
    stmt = select(Job).where(
        Job.source_id == source_id, Job.source_job_id == raw.source_job_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _replace_locations(session: AsyncSession, job: Job, raw: RawJob) -> None:
    """Persist the connector's parsed locations.

    These were previously dropped on the floor: connectors parsed them, and
    ingestion never wrote a JobLocation row. Nothing downstream could tell a
    Toronto co-op from a Singapore one, so eligibility and the Canada filters
    were operating on no location data at all.

    Rewritten rather than merged, because the board is the authority — a
    posting that moved cities should not keep its old one.
    """
    await session.execute(delete(JobLocation).where(JobLocation.job_id == job.id))
    for loc in raw.locations:
        text = (loc.raw_text or "").strip()
        if not text:
            continue
        session.add(
            JobLocation(
                job_id=job.id,
                raw_text=text[:255],
                city=(loc.city or None),
                region=(loc.region or None),
                country=(loc.country or None),
            )
        )


async def _assign_duplicate_group(session: AsyncSession, job: Job) -> None:
    """Lightweight dedup: reuse group of any job with same canonical URL or hash."""
    if job.canonical_application_url:
        stmt = select(Job).where(
            Job.canonical_application_url == job.canonical_application_url,
            Job.id != job.id,
            Job.duplicate_group_id.is_not(None),
        )
        other = (await session.execute(stmt)).scalars().first()
        if other:
            job.duplicate_group_id = other.duplicate_group_id
            return
    if job.content_hash:
        stmt = select(Job).where(
            Job.content_hash == job.content_hash,
            Job.id != job.id,
            Job.duplicate_group_id.is_not(None),
        )
        other = (await session.execute(stmt)).scalars().first()
        if other:
            job.duplicate_group_id = other.duplicate_group_id
            return
    job.duplicate_group_id = job.id  # becomes its own group's canonical


async def ingest_result(
    session: AsyncSession,
    source: JobSource,
    result: ConnectorResult,
) -> dict:
    """Persist a connector result. Idempotent per (source, source_job_id).

    Failure-isolated: a single bad record is logged as a ConnectorFailure and
    skipped rather than aborting the run.
    """
    now = datetime.now(UTC)
    stats = {"seen": 0, "new": 0, "updated": 0, "errors": 0}

    if result.not_modified:
        source.last_synced_at = now
        return stats

    for raw in result.raw_jobs:
        stats["seen"] += 1
        try:
            existing = await _find_existing(session, source.id, raw)
            remote_mode = infer_remote_mode(raw.description_text, raw.remote_mode)
            fresh = compute_freshness(
                now=now,
                source_posted_at=raw.source_posted_at,
                last_verified_at=now,
                application_deadline=None,
                source_status=raw.source_status,
            )
            if existing is None:
                job = Job(
                    source_id=source.id,
                    source_job_id=raw.source_job_id,
                    company_id=source.company_id,
                    title=raw.title,
                    normalized_title=normalize_title(raw.title),
                    description_text=raw.description_text,
                    department=raw.department,
                    employment_type=raw.employment_type,
                    remote_mode=remote_mode,
                    official_source_url=raw.official_source_url,
                    canonical_application_url=raw.canonical_application_url,
                    first_seen_at=now,
                    last_seen_at=now,
                    last_verified_at=now,
                    source_posted_at=raw.source_posted_at,
                    source_updated_at=raw.source_updated_at,
                    source_status=raw.source_status,
                    current_status="discovered",
                    source_priority=source.source_priority,
                    freshness_score=fresh,
                    content_hash=raw.content_hash,
                    inbox_category="new",
                    raw=raw.raw,
                )
                session.add(job)
                await session.flush()
                await _replace_locations(session, job, raw)
                await _assign_duplicate_group(session, job)
                session.add(
                    JobSnapshot(
                        job_id=job.id,
                        content_hash=raw.content_hash or "",
                        source_status=raw.source_status,
                        fetched_at=now,
                        raw=raw.raw,
                    )
                )
                stats["new"] += 1
            else:
                existing.last_seen_at = now
                existing.last_verified_at = now
                existing.source_status = raw.source_status
                existing.freshness_score = fresh
                await _replace_locations(session, existing, raw)
                if raw.content_hash and raw.content_hash != existing.content_hash:
                    existing.content_hash = raw.content_hash
                    existing.title = raw.title
                    existing.description_text = raw.description_text
                    existing.version += 1
                    session.add(
                        JobSnapshot(
                            job_id=existing.id,
                            content_hash=raw.content_hash,
                            source_status=raw.source_status,
                            fetched_at=now,
                            raw=raw.raw,
                        )
                    )
                    stats["updated"] += 1
        except Exception as exc:  # failure isolation — never abort the run
            stats["errors"] += 1
            log.warning("ingest error on %s: %s", raw.source_job_id, exc)
            session.add(
                ConnectorFailure(
                    source_id=source.id,
                    connector_key=source.connector_key,
                    stage="normalize",
                    error=str(exc)[:2000],
                )
            )

    source.last_synced_at = now
    if result.etag:
        source.etag = result.etag
    if result.last_modified:
        source.last_modified = result.last_modified
    source.health = "ok"
    return stats
