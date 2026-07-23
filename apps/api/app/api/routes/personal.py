"""Personal Context API — the single source of truth about the candidate.

Everything written here carries provenance. Facts imported from a resume are
`resume_extracted` and are NOT application-usable until the user confirms them
(docs/PERSONAL_CONTEXT.md). Nothing in this module ever infers a fact the user
did not supply.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_token
from app.core.provenance import ProvenanceSource, SensitivityLevel
from app.db.session import get_session
from app.models.ops import AuditLog
from app.models.personal import (
    ApplicationPreference,
    CandidateEducation,
    CandidateExperience,
    CandidateProfile,
    CandidateProject,
    CandidateSkill,
    PersonalContextItem,
    StandardAnswer,
    WorkAuthorization,
)
from app.models.user import User

router = APIRouter(prefix="/personal", tags=["personal"], dependencies=[Depends(require_token)])


# --------------------------------------------------------------------- schemas

class EducationIn(BaseModel):
    school: str
    degree: str | None = None          # bachelors / masters / phd
    field: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    gpa: str | None = None             # sensitive_legal
    source: str = ProvenanceSource.RESUME_EXTRACTED.value
    user_confirmed: bool = False


class ExperienceIn(BaseModel):
    company: str
    title: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    bullets: list[str] = Field(default_factory=list)
    source: str = ProvenanceSource.RESUME_EXTRACTED.value
    user_confirmed: bool = False


class ProjectIn(BaseModel):
    name: str
    description: str | None = None
    tech: list[str] = Field(default_factory=list)
    url: str | None = None
    source: str = ProvenanceSource.RESUME_EXTRACTED.value
    user_confirmed: bool = False


class SkillIn(BaseModel):
    name: str
    # Free text preserved verbatim — "basic" must never become "expert".
    proficiency: str | None = None
    years: float | None = None
    source: str = ProvenanceSource.RESUME_EXTRACTED.value
    user_confirmed: bool = False


class WorkAuthIn(BaseModel):
    country: str                        # ISO-2
    status: str | None = None
    needs_sponsorship: bool | None = None
    source: str = ProvenanceSource.USER_CONFIRMED.value
    user_confirmed: bool = True


class PreferencesIn(BaseModel):
    locations: list[str] = Field(default_factory=list)
    remote_pref: str | None = None
    min_salary: float | None = None
    salary_currency: str | None = None
    company_sizes: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    dealbreakers: list[str] = Field(default_factory=list)
    weight_overrides: dict = Field(default_factory=dict)


class ProfileIn(BaseModel):
    headline: str | None = None
    summary: str | None = None
    location: str | None = None
    links: dict = Field(default_factory=dict)


class ImportIn(BaseModel):
    """Bulk import. Defaults to unconfirmed so nothing silently becomes usable."""

    profile: ProfileIn | None = None
    education: list[EducationIn] = Field(default_factory=list)
    experiences: list[ExperienceIn] = Field(default_factory=list)
    projects: list[ProjectIn] = Field(default_factory=list)
    skills: list[SkillIn] = Field(default_factory=list)
    work_authorizations: list[WorkAuthIn] = Field(default_factory=list)
    preferences: PreferencesIn | None = None
    standard_answers: dict[str, str] = Field(default_factory=dict)
    items: dict[str, str] = Field(default_factory=dict)
    replace: bool = False


async def _uid(session: AsyncSession) -> str:
    uid = (await session.execute(select(User.id).limit(1))).scalar_one_or_none()
    if not uid:
        raise HTTPException(400, "no user exists yet")
    return uid


def _usable(source: str, confirmed: bool) -> bool:
    return confirmed and source in {
        ProvenanceSource.USER_CONFIRMED.value,
        ProvenanceSource.RESUME_EXTRACTED.value,
        ProvenanceSource.IMPORTED_DOCUMENT.value,
    }


# --------------------------------------------------------------------- routes

@router.post("/import")
async def import_context(
    payload: ImportIn, session: AsyncSession = Depends(get_session)
) -> dict:
    """Import a candidate profile. Unconfirmed by default."""
    user_id = await _uid(session)
    now = datetime.now(UTC)
    counts: dict[str, int] = {}

    if payload.replace:
        for model in (CandidateEducation, CandidateExperience, CandidateProject,
                      CandidateSkill, WorkAuthorization, ApplicationPreference,
                      StandardAnswer, PersonalContextItem, CandidateProfile):
            stmt = select(model).where(model.user_id == user_id)
            rows = (await session.execute(stmt)).scalars().all()
            for r in rows:
                await session.delete(r)
        await session.flush()

    if payload.profile:
        session.add(CandidateProfile(
            user_id=user_id, headline=payload.profile.headline,
            summary=payload.profile.summary, location=payload.profile.location,
            links=payload.profile.links,
            source=ProvenanceSource.RESUME_EXTRACTED.value, user_confirmed=False,
        ))
        counts["profile"] = 1

    for e in payload.education:
        session.add(CandidateEducation(
            user_id=user_id, school=e.school, degree=e.degree, field=e.field,
            start_date=e.start_date, end_date=e.end_date, gpa=e.gpa,
            source=e.source, user_confirmed=e.user_confirmed,
            confidence=1.0 if e.user_confirmed else 0.8,
        ))
    counts["education"] = len(payload.education)

    for x in payload.experiences:
        session.add(CandidateExperience(
            user_id=user_id, company=x.company, title=x.title,
            start_date=x.start_date, end_date=x.end_date, bullets=x.bullets,
            source=x.source, user_confirmed=x.user_confirmed,
            confidence=1.0 if x.user_confirmed else 0.8,
        ))
    counts["experiences"] = len(payload.experiences)

    for p in payload.projects:
        session.add(CandidateProject(
            user_id=user_id, name=p.name, description=p.description,
            tech=p.tech, url=p.url, source=p.source,
            user_confirmed=p.user_confirmed,
        ))
    counts["projects"] = len(payload.projects)

    for s in payload.skills:
        session.add(CandidateSkill(
            user_id=user_id, name=s.name, proficiency=s.proficiency, years=s.years,
            source=s.source, user_confirmed=s.user_confirmed,
            confidence=1.0 if s.user_confirmed else 0.8,
        ))
    counts["skills"] = len(payload.skills)

    for w in payload.work_authorizations:
        session.add(WorkAuthorization(
            user_id=user_id, country=w.country.upper(), status=w.status,
            needs_sponsorship=w.needs_sponsorship, source=w.source,
            user_confirmed=w.user_confirmed,
            sensitivity_level=SensitivityLevel.SENSITIVE_LEGAL.value,
        ))
    counts["work_authorizations"] = len(payload.work_authorizations)

    if payload.preferences:
        pr = payload.preferences
        session.add(ApplicationPreference(
            user_id=user_id, locations=pr.locations, remote_pref=pr.remote_pref,
            min_salary=pr.min_salary, salary_currency=pr.salary_currency,
            company_sizes=pr.company_sizes, industries=pr.industries,
            target_roles=pr.target_roles, dealbreakers=pr.dealbreakers,
            weight_overrides=pr.weight_overrides,
            source=ProvenanceSource.USER_CONFIRMED.value, user_confirmed=True,
        ))
        counts["preferences"] = 1

    for q, a in payload.standard_answers.items():
        session.add(StandardAnswer(
            user_id=user_id, question_key=q, answer=a,
            source=ProvenanceSource.USER_CONFIRMED.value, user_confirmed=True,
            can_use_for_application=True,
        ))
    counts["standard_answers"] = len(payload.standard_answers)

    for k, v in payload.items.items():
        session.add(PersonalContextItem(
            user_id=user_id, key=k, value=v,
            source=ProvenanceSource.RESUME_EXTRACTED.value, user_confirmed=False,
            can_use_for_application=False,
        ))
    counts["items"] = len(payload.items)

    session.add(AuditLog(actor="user", action="personal_context_import",
                         entity_type="personal_context", summary=str(counts),
                         meta={"replace": payload.replace, "at": now.isoformat()}))
    await session.commit()
    return {
        "imported": counts,
        "note": "Resume-extracted facts are UNCONFIRMED and cannot be used in an "
                "application until confirmed via POST /personal/confirm-all or "
                "per-item confirmation.",
    }


@router.get("")
async def get_context(session: AsyncSession = Depends(get_session)) -> dict:
    """Everything the system knows about the user, with provenance."""
    user_id = await _uid(session)

    async def rows(model):
        stmt = select(model).where(model.user_id == user_id)
        return (await session.execute(stmt)).scalars().all()

    edu = await rows(CandidateEducation)
    exp = await rows(CandidateExperience)
    proj = await rows(CandidateProject)
    sk = await rows(CandidateSkill)
    auth = await rows(WorkAuthorization)
    prefs = await rows(ApplicationPreference)
    answers = await rows(StandardAnswer)

    return {
        "education": [
            {"school": e.school, "degree": e.degree, "field": e.field,
             "end_date": e.end_date, "gpa_present": bool(e.gpa),
             "source": e.source, "user_confirmed": e.user_confirmed} for e in edu
        ],
        "experiences": [
            {"company": x.company, "title": x.title, "start": x.start_date,
             "end": x.end_date, "bullets": x.bullets, "source": x.source,
             "user_confirmed": x.user_confirmed} for x in exp
        ],
        "projects": [
            {"name": p.name, "tech": p.tech, "source": p.source,
             "user_confirmed": p.user_confirmed} for p in proj
        ],
        "skills": [
            {"name": s.name, "proficiency": s.proficiency, "source": s.source,
             "user_confirmed": s.user_confirmed} for s in sk
        ],
        "work_authorizations": [
            {"country": a.country, "status": a.status,
             "needs_sponsorship": a.needs_sponsorship,
             "user_confirmed": a.user_confirmed} for a in auth
        ],
        "preferences": [
            {"locations": p.locations, "remote_pref": p.remote_pref,
             "target_roles": p.target_roles, "dealbreakers": p.dealbreakers}
            for p in prefs
        ],
        "standard_answers": [
            {"question": a.question_key, "answer": a.answer,
             "usable": a.can_use_for_application} for a in answers
        ],
        "unconfirmed_count": sum(
            1 for r in (*edu, *exp, *proj, *sk, *auth) if not r.user_confirmed
        ),
    }


@router.post("/confirm-all")
async def confirm_all(
    confirm: str = Body(..., embed=True),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Confirm every imported fact at once.

    Requires an explicit acknowledgement string: confirming makes these facts
    usable in real applications, so it must be a deliberate act.
    """
    if confirm != "I CONFIRM THESE FACTS ARE ACCURATE":
        raise HTTPException(
            400, 'confirm must be exactly "I CONFIRM THESE FACTS ARE ACCURATE"'
        )
    user_id = await _uid(session)
    now = datetime.now(UTC)
    n = 0
    models: tuple[Any, ...] = (
        CandidateEducation, CandidateExperience, CandidateProject,
        CandidateSkill, WorkAuthorization, CandidateProfile,
    )
    for model in models:
        stmt = select(model).where(model.user_id == user_id)
        rows: list[Any] = list((await session.execute(stmt)).scalars().all())
        for r in rows:
            if not r.user_confirmed:
                r.user_confirmed = True
                r.confidence = 1.0
                if hasattr(r, "last_confirmed_at"):
                    r.last_confirmed_at = now
                if hasattr(r, "can_use_for_application"):
                    r.can_use_for_application = _usable(r.source, True)
                n += 1
    session.add(AuditLog(actor="user", action="personal_context_confirm_all",
                         entity_type="personal_context", summary=f"{n} facts confirmed"))
    await session.commit()
    return {"confirmed": n, "usable_for_applications": True}
