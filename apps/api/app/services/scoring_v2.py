"""Wires the v2 engines to real job/company/candidate rows and persists results.

Nothing here invents data: a company with no evidence rows scores as Unrated,
and candidate skills without recorded evidence strength default to the most
conservative level (listed-only).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.company.intelligence import (
    CompanyDimension,
    Evidence,
    SourceGrade,
    assess_company,
)
from app.eligibility.engine import detect_seniority, evaluate
from app.models.personal import CandidateSkill
from app.models.ranking_v2 import (
    ApplicationPriorityScore,
    CompanyEvidence,
    RoleClassificationRow,
)
from app.models.sourcing import Job, JobLocation
from app.parsing.jd_parser import parse_jd
from app.personal.service import build_candidate_facts
from app.ranking.gate import evaluate_gate
from app.ranking.modes import RankingMode, RankingProfile
from app.ranking.priority import PriorityResult, compute_priority
from app.roles.taxonomy import classify_role
from app.skills.ontology import (
    CandidateSkillEvidence,
    EvidenceStrength,
    JDSkill,
    compute_fit,
    extract_skills,
)

# Recorded proficiency -> evidence strength. Absent proficiency stays at the
# most conservative level rather than assuming competence.
_PROFICIENCY_STRENGTH = {
    "production": EvidenceStrength.PRODUCTION,
    "core": EvidenceStrength.CORE_OWNERSHIP,
    "internship": EvidenceStrength.INTERNSHIP,
    "project": EvidenceStrength.PERSONAL_PROJECT,
    "coursework": EvidenceStrength.COURSEWORK,
    "course": EvidenceStrength.COURSEWORK,
}


async def _candidate_skills(session: AsyncSession, user_id: str) -> list[CandidateSkillEvidence]:
    rows = (
        await session.execute(
            select(CandidateSkill).where(
                CandidateSkill.user_id == user_id,
                CandidateSkill.user_confirmed.is_(True),
            )
        )
    ).scalars().all()

    out: list[CandidateSkillEvidence] = []
    for r in rows:
        canon = extract_skills(r.name)
        skill = canon[0] if canon else r.name.lower()
        strength = _PROFICIENCY_STRENGTH.get(
            (r.proficiency or "").lower(), EvidenceStrength.LISTED_ONLY
        )
        out.append(CandidateSkillEvidence(skill=skill, strength=strength))
    return out


async def _company_evidence(session: AsyncSession, company_id: str | None) -> list[Evidence]:
    """Load graded evidence. No rows => genuinely unrated (not a guess)."""
    if not company_id:
        return []
    rows = (
        await session.execute(
            select(CompanyEvidence).where(
                CompanyEvidence.company_id == company_id,
                CompanyEvidence.still_valid.is_(True),
            )
        )
    ).scalars().all()

    out: list[Evidence] = []
    for r in rows:
        try:
            dim = CompanyDimension(r.supports_dimension)
            grade = SourceGrade(r.grade)
        except ValueError:
            continue  # unknown enum value: skip rather than guess
        out.append(
            Evidence(
                url=r.url, source_type=r.source_type, grade=grade,
                supports_dimension=dim, summary=r.summary or "",
                value=r.value, fetched_at=r.fetched_at,
                published_at=r.published_at, still_valid=r.still_valid,
            )
        )
    return out


async def score_job(
    session: AsyncSession,
    job: Job,
    user_id: str,
    *,
    mode: RankingMode = RankingMode.INTERNSHIP,
    persist: bool = True,
) -> PriorityResult:
    """Compute the v2 priority for one job and (optionally) persist it."""
    description = job.description_text or ""
    jd = parse_jd(description)

    facts = await build_candidate_facts(session, user_id)
    # The posting's location is a hard eligibility input, not decoration. Without
    # it a Canadian PR passed the gate on roles in Dubai, Brazil and Uruguay.
    location = (
        await session.execute(
            select(JobLocation.raw_text).where(JobLocation.job_id == job.id).limit(1)
        )
    ).scalar_one_or_none()
    # Seniority comes from the title, which the JD-text parser never sees, so
    # it is detected here and passed in. This is what keeps a "Senior Manager,
    # 10+ years" role out of a co-op student's eligible set.
    seniority = detect_seniority(job.title, jd.years_experience)
    company = assess_company(await _company_evidence(session, job.company_id))
    # Role family is a hard screen for a technical candidate: a non-technical
    # posting (sales, support, marketing) is off-target and gated out here
    # rather than ranked. Classified before the gate so its band can feed it.
    role = classify_role(job.title, description)
    gate = evaluate_gate(evaluate(
        jd, facts, location=location, seniority=seniority,
        role_band=role.band.value, role_type=role.role_type))

    jd_skills = [JDSkill(skill=s, required=True) for s in extract_skills(description)]
    fit = compute_fit(jd_skills, await _candidate_skills(session, user_id))

    deadline_soon = False
    if job.application_deadline:
        delta = (job.application_deadline - datetime.now(UTC)).total_seconds()
        deadline_soon = 0 <= delta <= 72 * 3600

    result = compute_priority(
        gate=gate,
        company=company,
        role=role,
        fit=fit,
        description=description,
        profile=RankingProfile.for_mode(mode),
        freshness=job.freshness_score or 0.5,
        effort_minutes=20,
        has_outcome_history=False,
        deadline_within_72h=deadline_soon,
    )

    if persist:
        session.add(
            RoleClassificationRow(
                job_id=job.id, role_type=role.role_type, band=role.band.value,
                confidence=role.confidence, technical_density=role.technical_density,
                transferability=role.transferability, evidence=role.evidence,
                signals_positive=role.signals_positive,
                signals_negative=role.signals_negative,
                needs_review=role.needs_review,
            )
        )
        session.add(
            ApplicationPriorityScore(
                job_id=job.id, user_id=user_id, ranking_mode=mode.value,
                eligibility_gate=result.eligibility.gate.value,
                company_tier=result.company_tier,
                company_tier_display=result.company_tier_display,
                role_band=result.role_band, role_type=result.role_type,
                company_platform_value=result.company_platform_value.conservative,
                role_strategic_value=result.role_strategic_value.conservative,
                current_candidate_fit=result.current_candidate_fit.conservative,
                team_project_quality=result.team_project_quality.conservative,
                career_optionality=result.career_optionality.conservative,
                evidence_coverage=result.evidence_coverage,
                application_priority=result.application_priority,
                opportunity_estimate=result.opportunity_estimate,
                recommendation=result.recommendation,
                interaction_rule=result.interaction_rule,
                why=result.why, why_not=result.why_not, unknowns=result.unknowns,
                calculated_at=datetime.now(UTC),
            )
        )
    return result


async def score_all_jobs(
    session: AsyncSession, user_id: str, *, mode: RankingMode = RankingMode.INTERNSHIP
) -> dict:
    jobs = (
        await session.execute(select(Job).where(Job.deleted_at.is_(None)))
    ).scalars().all()
    scored = 0
    for job in jobs:
        await score_job(session, job, user_id, mode=mode)
        scored += 1
    await session.commit()
    return {"scored": scored, "mode": mode.value, "formula_version": "v2"}


async def latest_scores(session: AsyncSession, job_ids: list[str]) -> dict[str, dict]:
    """Most recent v2 score per job, for list rendering."""
    if not job_ids:
        return {}
    rows = (
        await session.execute(
            select(ApplicationPriorityScore)
            .where(ApplicationPriorityScore.job_id.in_(job_ids))
            .order_by(ApplicationPriorityScore.created_at.desc())
        )
    ).scalars().all()

    out: dict[str, dict] = {}
    for r in rows:
        if r.job_id in out:
            continue  # first row wins (ordered desc)
        out[r.job_id] = {
            "eligibility": r.eligibility_gate,
            "company_tier": r.company_tier_display,
            "company_platform_value": r.company_platform_value,
            "role_category": r.role_band,
            "role_type": r.role_type,
            "role_strategic_value": r.role_strategic_value,
            "current_candidate_fit": r.current_candidate_fit,
            "team_project_quality": r.team_project_quality,
            "career_optionality": r.career_optionality,
            "evidence_coverage": r.evidence_coverage,
            "application_priority": r.application_priority,
            "opportunity_estimate": r.opportunity_estimate,
            "recommendation": r.recommendation,
            "interaction_rule": r.interaction_rule,
            "why": r.why,
            "why_not": r.why_not,
            "unknowns": r.unknowns,
        }
    return out
