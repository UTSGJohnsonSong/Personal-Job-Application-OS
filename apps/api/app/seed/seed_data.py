"""Seed FICTIONAL data only. Never contains the real user's personal data.

Run:  python -m app.seed.seed_data
Creates one fully-fictional test candidate, two ATS sources, ingests fictional
jobs, and computes eligibility + ranking so the UI has something to show.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.provenance import ProvenanceSource
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.eligibility.engine import CandidateFacts, evaluate
from app.ingestion.sync import ingest_result
from app.models.matching import (
    EligibilityResult,
    JobMatch,
    MatchDimension,
    RankingProfile,
    RankingVersion,
)
from app.models.personal import (
    ApplicationPreference,
    CandidateEducation,
    CandidateSkill,
    WorkAuthorization,
)
from app.models.sourcing import Company, Job, JobSource
from app.models.user import User, UserSettings
from app.parsing.jd_parser import parse_jd
from app.ranking.engine import RankInputs, rank
from app.schemas.connector import ConnectorResult, RawJob, RawLocation

SEED_EMAIL = "test.candidate@example.test"  # FICTIONAL

_FICTIONAL_JOBS = [
    RawJob(
        source_job_id="1001",
        title="Software Engineer, Backend",
        description_text=(
            "We are hiring a Backend Engineer. Bachelor's degree required. "
            "3+ years experience with Python and PostgreSQL."
        ),
        remote_mode="hybrid",
        locations=[RawLocation(raw_text="Toronto, ON, Canada")],
        official_source_url="https://boards.greenhouse.io/exampleco/jobs/1001",
        canonical_application_url="https://boards.greenhouse.io/exampleco/jobs/1001",
        source_posted_at=datetime(2026, 7, 15, tzinfo=UTC),
        content_hash="seed-hash-1001",
        raw={},
    ),
    RawJob(
        source_job_id="1002",
        title="Machine Learning Engineer",
        description_text="Work on ML systems. PhD required. Python, PyTorch.",
        remote_mode="onsite",
        locations=[RawLocation(raw_text="San Francisco, CA, United States")],
        official_source_url="https://jobs.ashbyhq.com/exampleco/ashby-777",
        canonical_application_url="https://jobs.ashbyhq.com/exampleco/ashby-777/application",
        source_posted_at=datetime(2026, 7, 10, tzinfo=UTC),
        content_hash="seed-hash-1002",
        raw={},
    ),
]


async def seed() -> None:
    async with SessionLocal() as session:
        existing = (
            await session.execute(select(User).where(User.email == SEED_EMAIL))
        ).scalar_one_or_none()
        if existing:
            print("seed: fictional user already present, skipping")
            return

        user = User(email=SEED_EMAIL, password_hash=hash_password("dev-password-123"))
        session.add(user)
        await session.flush()
        session.add(UserSettings(user_id=user.id))

        # Confirmed, application-usable fictional context.
        session.add(CandidateEducation(
            user_id=user.id, school="Fictional University", degree="bachelors",
            field="Computer Science", source=ProvenanceSource.USER_CONFIRMED.value,
            user_confirmed=True, confidence=1.0,
        ))
        for sk in ("python", "postgresql", "sql", "fastapi"):
            session.add(CandidateSkill(
                user_id=user.id, name=sk, source=ProvenanceSource.USER_CONFIRMED.value,
                user_confirmed=True, confidence=1.0,
            ))
        session.add(WorkAuthorization(
            user_id=user.id, country="CA", status="permanent_resident",
            needs_sponsorship=False, source=ProvenanceSource.USER_CONFIRMED.value,
            user_confirmed=True,
        ))
        session.add(ApplicationPreference(
            user_id=user.id, locations=["Toronto", "Remote"], remote_pref="hybrid",
            target_roles=["engineer", "backend"], industries=["software"],
            source=ProvenanceSource.USER_CONFIRMED.value, user_confirmed=True,
        ))

        # Ranking profile/version.
        profile = RankingProfile(user_id=user.id, name="default")
        session.add(profile)
        await session.flush()
        version = RankingVersion(profile_id=profile.id, version_label="v1",
                                 weights={}, created_reason="seed default")
        session.add(version)
        await session.flush()
        profile.active_version_id = version.id

        # Company + sources.
        company = Company(name="ExampleCo", normalized_name="exampleco")
        session.add(company)
        await session.flush()
        gh = JobSource(connector_key="greenhouse", external_id="exampleco",
                       display_name="ExampleCo (Greenhouse)", company_id=company.id)
        session.add(gh)
        await session.flush()

        # Ingest fictional jobs.
        await ingest_result(session, gh, ConnectorResult(raw_jobs=_FICTIONAL_JOBS))
        await session.flush()

        # Eligibility + ranking for each job.
        facts = CandidateFacts(highest_degree="bachelors", degree_rank=2,
                               work_auth_countries={"CA"}, needs_sponsorship=False)
        skills = {"python", "postgresql", "sql", "fastapi"}
        jobs = (await session.execute(select(Job).where(Job.source_id == gh.id))).scalars().all()
        for job in jobs:
            jd = parse_jd(job.description_text)
            rep = evaluate(jd, facts)
            session.add(EligibilityResult(
                job_id=job.id, user_id=user.id, verdict=rep.verdict.value,
                reasons=rep.reasons, jd_evidence=rep.jd_evidence,
                context_evidence=rep.context_evidence, conflicts=rep.conflicts,
                unknowns=rep.unknowns, needs_user_confirmation=rep.needs_user_confirmation,
            ))
            jd_skills = {w for w in ("python", "postgresql", "sql", "pytorch")
                         if w in (job.description_text or "").lower()}
            result = rank(RankInputs(
                jd=jd, eligibility=rep, candidate_skills=skills, jd_skills=jd_skills,
                target_roles={"engineer", "backend"}, normalized_title=job.normalized_title,
                remote_mode=job.remote_mode, preferred_remote="hybrid", location_ok=True,
                salary_ok=None, freshness_score=job.freshness_score, company_quality=0.7,
                estimated_minutes=12, historical_outcome_rate=None,
            ))
            match = JobMatch(
                job_id=job.id, user_id=user.id, ranking_version_id=version.id,
                total_score=result.total_score, confidence=result.confidence,
                strategy=result.strategy, why_recommended=result.why_recommended,
                why_not=result.why_not, suggested_minutes=result.suggested_minutes,
            )
            session.add(match)
            await session.flush()
            for d in result.dimensions:
                session.add(MatchDimension(
                    match_id=match.id, name=d.name, score=d.score, weight=d.weight,
                    confidence=d.confidence, uncertainty=d.uncertainty,
                ))
            job.inbox_category = "strong_match" if result.total_score >= 0.6 else "manual_review"

        await session.commit()
        print(f"seed: created fictional user {user.email} with {len(jobs)} jobs")


if __name__ == "__main__":
    asyncio.run(seed())
