"""Rescoring must update, not append — and must pick the same location twice.

Both tables held current state but neither had a uniqueness constraint, and
`score_job` used a bare `session.add()`. `score_all_jobs` walks every job, so
each recompute or pool refresh appended a whole new generation: by 2026-07-25
`application_priority_scores` and `role_classifications` each held 111,166 rows
for 10,923 jobs.

The duplication also hid a correctness bug. The location read used `.limit(1)`
with no ORDER BY, so a posting listing several cities handed the eligibility
gate a different city on different runs — and since location is a HARD gate
input, two rows for the same job could disagree on PASS vs REVIEW. Readers took
"latest by created_at", which made that survivable instead of impossible.

These tests pin both halves: one row per job after repeated scoring, and a
deterministic, reachability-preferring location choice.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.ranking_v2 import ApplicationPriorityScore, RoleClassificationRow
from app.models.sourcing import Job, JobLocation, JobSource
from app.models.user import User
from app.ranking.modes import RankingMode
from app.services.scoring_v2 import _job_location, score_job


async def _uid(session) -> str:
    existing = (await session.execute(select(User).limit(1))).scalars().first()
    if existing is None:
        user = User(email=f"idem{datetime.now().timestamp()}@example.test", password_hash="x")
        session.add(user)
        await session.flush()
        return user.id
    return existing.id


async def _job(session, *, title="Data Engineer", locations: list[str] | None = None) -> Job:
    stamp = datetime.now().timestamp()
    src = JobSource(connector_key="greenhouse", external_id=f"idem{stamp}", display_name="Ex")
    session.add(src)
    await session.flush()
    job = Job(
        source_id=src.id, source_job_id=f"j{stamp}", title=title,
        normalized_title=title.lower(), first_seen_at=datetime.now(UTC),
        description_text="Build and maintain data pipelines using python and sql.",
        canonical_application_url=f"https://example.test/{stamp}",
        source_status="open", freshness_score=0.9,
    )
    session.add(job)
    await session.flush()
    for raw in locations or []:
        session.add(JobLocation(job_id=job.id, raw_text=raw))
    await session.commit()
    return job


@pytest.mark.asyncio
async def test_rescoring_a_job_updates_its_row_instead_of_adding_one(session):
    user_id = await _uid(session)
    job = await _job(session, locations=["Toronto, Ontario, Canada"])

    for _ in range(3):
        await score_job(session, job, user_id, mode=RankingMode.INTERNSHIP)
        await session.commit()

    scores = (
        await session.execute(
            select(ApplicationPriorityScore).where(ApplicationPriorityScore.job_id == job.id)
        )
    ).scalars().all()
    roles = (
        await session.execute(
            select(RoleClassificationRow).where(RoleClassificationRow.job_id == job.id)
        )
    ).scalars().all()

    assert len(scores) == 1, f"three runs produced {len(scores)} priority rows"
    assert len(roles) == 1, f"three runs produced {len(roles)} classification rows"


@pytest.mark.asyncio
async def test_repeated_scoring_never_yields_conflicting_gates(session):
    """The symptom the duplication hid: one job, two verdicts."""
    user_id = await _uid(session)
    job = await _job(session, locations=["Dubai, UAE", "Toronto, Ontario, Canada"])

    gates = []
    for _ in range(4):
        result = await score_job(session, job, user_id, mode=RankingMode.INTERNSHIP)
        await session.commit()
        gates.append(result.eligibility.gate.value)

    assert len(set(gates)) == 1, f"the same job produced different gates across runs: {gates}"


@pytest.mark.asyncio
async def test_multi_city_posting_is_judged_on_the_reachable_city(session):
    """A Toronto-and-Dubai requisition is a Toronto job — you apply to it once."""
    job = await _job(session, locations=["Dubai, UAE", "Toronto, Ontario, Canada"])
    chosen = await _job_location(session, job.id)
    assert chosen == "Toronto, Ontario, Canada"


@pytest.mark.asyncio
async def test_location_choice_is_stable_when_none_are_reachable(session):
    """No Canadian option: the choice is decided by content, not by row id.

    Ordering by id would pass this test by luck — ids are random hex, and
    `_replace_locations` regenerates them on every sync, so the "first" row
    would change after each re-ingestion. Ordering by `raw_text` makes the pick
    a property of the posting.
    """
    cities = ["Singapore", "Dubai, UAE", "London, UK"]
    job = await _job(session, locations=cities)
    picks = {await _job_location(session, job.id) for _ in range(4)}
    assert picks == {min(cities)}, f"expected the content-first city, got {picks}"


@pytest.mark.asyncio
async def test_a_posting_with_no_location_reports_unknown_not_a_guess(session):
    job = await _job(session, locations=[])
    assert await _job_location(session, job.id) is None
