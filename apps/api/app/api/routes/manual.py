"""Manual job entry.

Not every job arrives through a connector: referrals, school portals and
company sites without a public JSON board all need a hand-entered record.
Manually entered jobs are marked with a distinct source so they are never
confused with connector-verified postings, and their freshness is never
auto-asserted — the user owns the truth about them.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_token
from app.db.session import get_session
from app.ingestion.normalize import normalize_company, normalize_title
from app.models.application import Application
from app.models.ops import AuditLog
from app.models.sourcing import Company, Job, JobSource
from app.models.user import User

router = APIRouter(prefix="/manual", tags=["manual"], dependencies=[Depends(require_token)])

MANUAL_CONNECTOR_KEY = "manual_entry"


class ManualJobIn(BaseModel):
    company_name: str
    title: str
    description: str | None = None
    apply_url: str | None = None
    location: str | None = None
    employment_type: str | None = None
    remote_mode: str | None = None
    application_deadline: datetime | None = None
    source_posted_at: datetime | None = None
    # What the user knows about their own progress. Deliberately excludes
    # `submitted`: reaching submitted requires the confirmation flow.
    initial_status: str = "saved"
    note: str | None = None


async def _sole_user_id(session: AsyncSession) -> str:
    uid = (await session.execute(select(User.id).limit(1))).scalar_one_or_none()
    if not uid:
        raise HTTPException(400, "no user exists yet")
    return uid


async def _get_or_create_company(session: AsyncSession, name: str) -> Company:
    norm = normalize_company(name)
    existing = (
        await session.execute(select(Company).where(Company.normalized_name == norm))
    ).scalar_one_or_none()
    if existing:
        return existing
    company = Company(name=name, normalized_name=norm)
    session.add(company)
    await session.flush()
    return company


async def _get_or_create_manual_source(
    session: AsyncSession, company: Company
) -> JobSource:
    existing = (
        await session.execute(
            select(JobSource).where(
                JobSource.connector_key == MANUAL_CONNECTOR_KEY,
                JobSource.external_id == company.normalized_name,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    source = JobSource(
        connector_key=MANUAL_CONNECTOR_KEY,
        external_id=company.normalized_name,
        display_name=f"{company.name} (manual entry)",
        company_id=company.id,
        source_priority=1,  # a company's own site is still first-party
        enabled=False,       # nothing to sync; entered by hand
        health="manual",
    )
    session.add(source)
    await session.flush()
    return source


@router.post("/jobs")
async def create_manual_job(
    payload: ManualJobIn, session: AsyncSession = Depends(get_session)
) -> dict:
    """Record a job the user found outside any connector."""
    if payload.initial_status == "submitted":
        raise HTTPException(
            409,
            "`submitted` cannot be set here — a real submission requires the "
            "per-job confirmation flow. Record it as application_started and "
            "confirm separately, or set the status manually if it was submitted "
            "outside this system.",
        )

    user_id = await _sole_user_id(session)
    company = await _get_or_create_company(session, payload.company_name)
    source = await _get_or_create_manual_source(session, company)
    now = datetime.now(UTC)

    job = Job(
        source_id=source.id,
        source_job_id=f"manual-{normalize_title(payload.title)}-{int(now.timestamp())}",
        company_id=company.id,
        title=payload.title,
        normalized_title=normalize_title(payload.title),
        description_text=payload.description,
        employment_type=payload.employment_type,
        remote_mode=payload.remote_mode,
        official_source_url=payload.apply_url,
        canonical_application_url=payload.apply_url,
        first_seen_at=now,
        last_seen_at=now,
        # Manual entries are NOT auto-verified: we have not checked the source.
        last_verified_at=None,
        source_posted_at=payload.source_posted_at,
        application_deadline=payload.application_deadline,
        source_status="unknown",
        current_status="discovered",
        source_priority=1,
        freshness_score=0.0,   # unknown, not "fresh"
        inbox_category="manual_review",
        raw={"entered_manually": True, "note": payload.note},
    )
    session.add(job)
    await session.flush()
    job.duplicate_group_id = job.id

    application = Application(
        user_id=user_id, job_id=job.id, status=payload.initial_status,
        queued_at=now, queue_note=payload.note,
        last_status_change_at=now,
    )
    session.add(application)

    session.add(AuditLog(
        actor="user", action="manual_job_entry", entity_type="job", entity_id=job.id,
        summary=f"{payload.company_name} — {payload.title}",
        meta={"source": "manual_entry", "status": payload.initial_status},
    ))
    await session.commit()

    return {
        "job_id": job.id,
        "application_id": application.id,
        "company_id": company.id,
        "status": application.status,
        "warnings": [
            "Source status is unknown — this posting has not been verified by the system.",
            "Freshness is 0 because the system has not checked whether it is still open.",
        ],
    }


@router.post("/purge-demo-data")
async def purge_demo_data(
    confirm: str = Body(..., embed=True),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Delete the fictional seed data.

    Requires `confirm == "PURGE DEMO DATA"` so it cannot fire by accident.

    Removes the seeded jobs/company/source and — importantly — the fictional
    PERSONAL CONTEXT (fake school, skills, work authorization, preferences).
    Leaving those behind would mean every real job is judged against a candidate
    who is not the user. The user row itself is kept as the account shell.
    """
    if confirm != "PURGE DEMO DATA":
        raise HTTPException(400, 'confirm must be exactly "PURGE DEMO DATA"')

    from app.models.ammo import AmmoBlock
    from app.models.application import (
        ApplicationAnswer,
        ApplicationConfirmation,
        ApplicationEvent,
        ApplicationPacket,
        GeneratedDocument,
    )
    from app.models.matching import (
        EligibilityResult,
        JobMatch,
        MatchDimension,
        MatchEvidence,
    )
    from app.models.personal import (
        ApplicationPreference,
        CandidateEducation,
        CandidateExperience,
        CandidateProject,
        CandidateSkill,
        PersonalContextItem,
        StandardAnswer,
        WorkAuthorization,
    )
    from app.models.ranking_v2 import ApplicationPriorityScore, RoleClassificationRow
    from app.models.sourcing import JobSnapshot

    deleted: dict[str, int] = {}

    async def wipe(model, label: str) -> None:
        rows = (await session.execute(select(model))).scalars().all()
        for r in rows:
            await session.delete(r)
        deleted[label] = len(rows)
        await session.flush()

    # Order matters: children before parents.
    for model, label in (
        (MatchEvidence, "match_evidence"),
        (MatchDimension, "match_dimensions"),
        (JobMatch, "job_matches"),
        (EligibilityResult, "eligibility_results"),
        (ApplicationPriorityScore, "application_priority_scores"),
        (RoleClassificationRow, "role_classifications"),
        (ApplicationAnswer, "application_answers"),
        (GeneratedDocument, "generated_documents"),
        (ApplicationConfirmation, "application_confirmations"),
        (ApplicationEvent, "application_events"),
        (Application, "applications"),
        (ApplicationPacket, "application_packets"),
        (JobSnapshot, "job_snapshots"),
        (Job, "jobs"),
        (JobSource, "job_sources"),
        (Company, "companies"),
        # Fictional personal context — must not survive into real judgements.
        (CandidateEducation, "candidate_education"),
        (CandidateSkill, "candidate_skills"),
        (CandidateExperience, "candidate_experiences"),
        (CandidateProject, "candidate_projects"),
        (WorkAuthorization, "work_authorizations"),
        (ApplicationPreference, "application_preferences"),
        (StandardAnswer, "standard_answers"),
        (PersonalContextItem, "personal_context_items"),
        (AmmoBlock, "ammo_blocks"),
    ):
        await wipe(model, label)

    session.add(AuditLog(
        actor="user", action="purge_demo_data", entity_type="database",
        summary="fictional seed data purged", meta=deleted,
    ))
    await session.commit()
    return {
        "purged": deleted,
        "kept": ["users (account shell)", "audit_logs (append-only)"],
        "next": "Personal Context is now empty — nothing will be judged against "
                "fictional facts. Enter your real profile before trusting any score.",
    }


@router.post("/companies")
async def create_company(
    name: str = Body(..., embed=True), session: AsyncSession = Depends(get_session)
) -> dict:
    """Register a company so evidence can be attached to it before any job exists."""
    company = await _get_or_create_company(session, name)
    await session.commit()
    return {"company_id": company.id, "name": company.name,
            "normalized_name": company.normalized_name}
