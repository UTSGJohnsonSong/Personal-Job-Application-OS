from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.provenance import ProvenanceSource, can_use_for_application
from app.eligibility.engine import CandidateFacts
from app.models.personal import (
    ApplicationPreference,
    CandidateEducation,
    CandidateSkill,
    PersonalContextItem,
    WorkAuthorization,
)

_DEGREE_RANK = {"associate": 1, "bachelors": 2, "masters": 3, "phd": 4}


async def confirm_item(session: AsyncSession, item: PersonalContextItem) -> PersonalContextItem:
    """Mark a context item user-confirmed and application-usable."""
    item.user_confirmed = True
    item.source = ProvenanceSource.USER_CONFIRMED.value
    item.confidence = 1.0
    item.last_confirmed_at = datetime.now(UTC)
    item.can_use_for_application = can_use_for_application(
        ProvenanceSource.USER_CONFIRMED, True
    )
    return item


async def build_candidate_facts(session: AsyncSession, user_id: str) -> CandidateFacts:
    """Assemble ONLY confirmed, application-usable facts for eligibility.

    Unconfirmed/inferred data is intentionally excluded — the engine treats a
    missing field as 'unknown' and never guesses (see docs/PERSONAL_CONTEXT.md).
    """
    facts = CandidateFacts()

    # Highest confirmed degree.
    edu = (
        await session.execute(
            select(CandidateEducation).where(
                CandidateEducation.user_id == user_id,
                CandidateEducation.user_confirmed.is_(True),
            )
        )
    ).scalars().all()
    best = None
    for e in edu:
        rank = _DEGREE_RANK.get((e.degree or "").lower())
        if rank and (best is None or rank > best):
            best = rank
            facts.highest_degree = (e.degree or "").lower()
    facts.degree_rank = best

    # Work authorization (confirmed only).
    auths = (
        await session.execute(
            select(WorkAuthorization).where(
                WorkAuthorization.user_id == user_id,
                WorkAuthorization.user_confirmed.is_(True),
            )
        )
    ).scalars().all()
    for a in auths:
        facts.work_auth_countries.add(a.country.upper())
        if a.needs_sponsorship is not None:
            facts.needs_sponsorship = a.needs_sponsorship

    # Preferences → target employment types.
    pref = (
        await session.execute(
            select(ApplicationPreference).where(ApplicationPreference.user_id == user_id)
        )
    ).scalars().first()
    if pref and pref.weight_overrides:
        wo = pref.weight_overrides
        et = wo.get("target_employment_types")
        if et:
            facts.target_employment_types = set(et)
        ts = wo.get("target_seniority")
        if ts:
            facts.target_seniority = set(ts)
        ye = wo.get("years_experience")
        if ye is not None:
            facts.years_experience = float(ye)

    return facts


async def confirmed_skill_set(session: AsyncSession, user_id: str) -> set[str]:
    rows = (
        await session.execute(
            select(CandidateSkill.name).where(
                CandidateSkill.user_id == user_id,
                CandidateSkill.user_confirmed.is_(True),
            )
        )
    ).scalars().all()
    return {s.lower() for s in rows}
