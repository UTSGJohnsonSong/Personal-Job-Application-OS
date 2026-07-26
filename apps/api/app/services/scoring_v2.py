"""Wires the v2 engines to real job/company/candidate rows and persists results.

Nothing here invents data: a company with no evidence rows scores as Unrated,
and candidate skills without recorded evidence strength default to the most
conservative level (listed-only).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.company.access import preferred_location
from app.company.intelligence import (
    CompanyDimension,
    CompanyIntelligence,
    Evidence,
    SourceGrade,
    assess_company,
    from_registry_profile,
)
from app.company.profiles import resolve as resolve_company_profile
from app.eligibility.engine import CandidateFacts, detect_seniority, evaluate
from app.models.personal import CandidateSkill
from app.models.ranking_v2 import (
    ApplicationPriorityScore,
    CompanyEvidence,
    RoleClassificationRow,
)
from app.models.sourcing import Company, Job, JobLocation
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


class ScoringDataError(RuntimeError):
    """The scoring tables are in a shape the code cannot safely write to.

    Raised instead of letting `MultipleResultsFound` escape, because that
    exception names neither the job nor the fix. The realistic cause is new code
    running against a database where migration b1c74e9a2f30 has not been
    applied — a rollback, a hand-started worker, or a failed upgrade.
    """


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


async def _assess_company_for_job(
    session: AsyncSession,
    company_id: str | None,
    cache: dict[str, CompanyIntelligence] | None = None,
) -> CompanyIntelligence:
    """The registry is the authority when it has a profile; evidence ledger otherwise.

    Without this, every job scored `company_platform_value=50, tier="D"` no
    matter which company it was for — `CompanyEvidence` has never had a row
    written to it, so `assess_company()` always fell back to its neutral
    prior. `app/company/profiles.py` is the 262-company hand-researched
    registry that already drives the tier badge shown in the inbox
    (app/services/inbox.py); this makes the per-job ranking number agree
    with the badge instead of silently ignoring it.
    """
    # There are 262 employers and ten thousand postings, so without a cache this
    # runs the same lookup forty times per company on a full pass — a round trip
    # to the database each time, which on a hosted instance is most of the cost
    # of scoring one posting.
    if cache is not None and company_id and company_id in cache:
        return cache[company_id]

    result: CompanyIntelligence | None = None
    if company_id:
        company = await session.get(Company, company_id)
        if company:
            profile = resolve_company_profile(company.normalized_name) or (
                resolve_company_profile(company.name)
            )
            if profile:
                result = from_registry_profile(profile)
    if result is None:
        result = assess_company(await _company_evidence(session, company_id))
    if cache is not None and company_id:
        cache[company_id] = result
    return result


async def _job_location(session: AsyncSession, job_id: str) -> str | None:
    """The location the eligibility gate should judge.

    A posting can carry several `JobLocation` rows — one requisition advertised
    in several cities. You apply to it once, so the most reachable city is the
    one that decides eligibility.

    This used to be `.limit(1)` with no ORDER BY, which meant whichever row the
    query plan happened to return. Since location is a HARD gate input, the same
    job could score PASS on one run and FAIL on the next — which is how rows for
    one job ended up disagreeing with each other. `preferred_location` ranks by
    reachability class rather than picking the first row, because the gate has
    three outcomes and an unreachable city must not outrank an unresolved one.
    """
    rows = (
        await session.execute(
            select(JobLocation.raw_text).where(JobLocation.job_id == job_id)
        )
    ).scalars().all()
    return preferred_location(rows)


async def score_job(
    session: AsyncSession,
    job: Job,
    user_id: str,
    *,
    mode: RankingMode = RankingMode.INTERNSHIP,
    persist: bool = True,
    facts: CandidateFacts | None = None,
    skills: list[CandidateSkillEvidence] | None = None,
    company_cache: dict[str, CompanyIntelligence] | None = None,
) -> PriorityResult:
    """Compute the v2 priority for one job and (optionally) persist it.

    `facts` and `skills` describe the candidate, not the posting, so a batch
    run passes them in once instead of re-reading them per job — that was two
    extra queries on every one of ~10k postings.
    """
    description = job.description_text or ""
    jd = parse_jd(description)

    if facts is None:
        facts = await build_candidate_facts(session, user_id)
    # The posting's location is a hard eligibility input, not decoration. Without
    # it a Canadian PR passed the gate on roles in Dubai, Brazil and Uruguay.
    location = await _job_location(session, job.id)
    # Seniority comes from the title, which the JD-text parser never sees, so
    # it is detected here and passed in. This is what keeps a "Senior Manager,
    # 10+ years" role out of a co-op student's eligible set.
    seniority = detect_seniority(job.title, jd.years_experience)
    company = await _assess_company_for_job(session, job.company_id, company_cache)
    # Role family is a hard screen for a technical candidate: a non-technical
    # posting (sales, support, marketing) is off-target and gated out here
    # rather than ranked. Classified before the gate so its band can feed it.
    role = classify_role(job.title, description)
    gate = evaluate_gate(evaluate(
        jd, facts, location=location, seniority=seniority,
        role_band=role.band.value, role_type=role.role_type))

    jd_skills = [JDSkill(skill=s, required=True) for s in extract_skills(description)]
    if skills is None:
        skills = await _candidate_skills(session, user_id)
    fit = compute_fit(jd_skills, skills)

    result = compute_priority(
        gate=gate,
        company=company,
        role=role,
        fit=fit,
        description=description,
        profile=RankingProfile.for_mode(mode),
        freshness=job.freshness_score or 0.5,
        source_status=job.source_status or "open",
        application_deadline=job.application_deadline,
        effort_minutes=20,
    )

    if persist:
        # UPDATE in place, never append. Both tables hold current state, not a
        # history of every run: `score_all_jobs` walks the whole table, so an
        # insert-only path multiplied both tables by the number of recomputes
        # (10.2x by 2026-07-25). Readers hid it by taking "latest by created_at",
        # which made contradictory rows survivable instead of impossible.
        await _upsert_role_classification(session, job.id, role)
        await _upsert_priority_score(session, job.id, user_id, mode, result)
    return result


async def _upsert_role_classification(session: AsyncSession, job_id: str, role) -> None:
    values = dict(
        role_type=role.role_type, band=role.band.value,
        confidence=role.confidence, technical_density=role.technical_density,
        transferability=role.transferability, evidence=role.evidence,
        signals_positive=role.signals_positive,
        signals_negative=role.signals_negative,
        needs_review=role.needs_review,
    )
    rows = (
        await session.execute(
            select(RoleClassificationRow).where(RoleClassificationRow.job_id == job_id)
        )
    ).scalars().all()
    if len(rows) > 1:
        raise ScoringDataError(
            f"job {job_id!r} has {len(rows)} role_classifications rows; the "
            f"uniqueness migration (b1c74e9a2f30) has not been applied to this "
            f"database — run `alembic upgrade head` before scoring"
        )
    if not rows:
        session.add(RoleClassificationRow(job_id=job_id, **values))
        return
    for field, value in values.items():
        setattr(rows[0], field, value)


async def _upsert_priority_score(
    session: AsyncSession,
    job_id: str,
    user_id: str,
    mode: RankingMode,
    result: PriorityResult,
) -> None:
    # `manually_overridden` and `override_reason` are deliberately absent: they
    # are the user's judgement about this job, and rescoring refreshes the
    # computed numbers AROUND them rather than through them. The omission is the
    # protection — adding either field here would silently clear a user override
    # on the next recompute. (No code writes them yet; the column pair is
    # reserved for an override UI that does not exist. `test_scoring_idempotence`
    # pins the behaviour so the guarantee survives that UI being built.)
    values = dict(
        formula_version=result.formula_version,
        weights_version=RankingProfile.for_mode(mode).version_label,
        eligibility_gate=result.eligibility.gate.value,
        company_tier=result.company_tier,
        company_tier_display=result.company_tier_display,
        role_band=result.role_band, role_type=result.role_type,
        company_platform_value=result.company_platform_value.conservative,
        role_strategic_value=result.role_strategic_value.conservative,
        current_candidate_fit=result.current_candidate_fit.conservative,
        team_project_quality=result.team_project_quality.conservative,
        career_optionality=result.career_optionality.conservative,
        opportunity_viability=result.opportunity_viability.conservative,
        evidence_coverage=result.evidence_coverage,
        application_priority=result.application_priority,
        action_urgency=result.action_urgency,
        application_effort_minutes=result.application_effort_minutes,
        recommendation=result.recommendation,
        interaction_rule=result.interaction_rule,
        why=result.why, why_not=result.why_not, unknowns=result.unknowns,
        calculated_at=datetime.now(UTC),
    )
    rows = (
        await session.execute(
            select(ApplicationPriorityScore).where(
                ApplicationPriorityScore.job_id == job_id,
                ApplicationPriorityScore.user_id == user_id,
                ApplicationPriorityScore.ranking_mode == mode.value,
            )
        )
    ).scalars().all()
    if len(rows) > 1:
        raise ScoringDataError(
            f"job {job_id!r} has {len(rows)} priority rows for user={user_id} "
            f"mode={mode.value}; the uniqueness migration (b1c74e9a2f30) has not "
            f"been applied to this database — run `alembic upgrade head` first"
        )
    if not rows:
        session.add(
            ApplicationPriorityScore(
                job_id=job_id, user_id=user_id, ranking_mode=mode.value, **values
            )
        )
        return
    for field, value in values.items():
        setattr(rows[0], field, value)


# How many postings are held in memory at once. Scoring genuinely needs
# `description_text` — it parses the posting body — so unlike the read paths
# this cannot be made cheaper by selecting fewer columns; it has to be made
# smaller. At ~10k postings a single pass held the whole table plus every
# parsed intermediate, which is what killed the 512MB deployed container
# mid-refresh: the postings landed, the scores never did, and the board showed
# one seeded row while the inbox counted ten thousand.
SCORING_BATCH = 200


async def score_all_jobs(
    session: AsyncSession,
    user_id: str,
    *,
    mode: RankingMode = RankingMode.INTERNSHIP,
    batch_size: int = SCORING_BATCH,
    only_unscored: bool = False,
    limit: int | None = None,
) -> dict:
    """Rescore live postings, a batch at a time.

    Committing per batch is not only about memory: a run that dies partway now
    leaves the batches it finished, so re-running makes progress instead of
    starting from nothing.

    `only_unscored` turns that into a resumable job. On a small instance a full
    pass over ten thousand postings is long enough that something can interrupt
    it, and the postings it already scored do not need doing again — this skips
    them, so repeated runs converge instead of restarting.
    """
    stmt = select(Job.id).where(Job.deleted_at.is_(None))
    if only_unscored:
        stmt = stmt.where(
            ~select(ApplicationPriorityScore.id)
            .where(
                ApplicationPriorityScore.job_id == Job.id,
                ApplicationPriorityScore.user_id == user_id,
                ApplicationPriorityScore.ranking_mode == mode.value,
            )
            .exists()
        )
    pending = list((await session.execute(stmt)).scalars().all())
    # `limit` caps one call so it finishes inside an HTTP request. Ten thousand
    # postings take minutes; a caller that wants them all loops until
    # `remaining` reaches zero and gets progress in between, rather than one
    # request that a proxy will cut off halfway.
    job_ids = pending[:limit] if limit else pending

    # Read the candidate once, not once per posting.
    facts = await build_candidate_facts(session, user_id)
    skills = await _candidate_skills(session, user_id)
    company_cache: dict[str, CompanyIntelligence] = {}

    scored = 0
    failed: list[str] = []
    for start in range(0, len(job_ids), batch_size):
        chunk = job_ids[start : start + batch_size]
        jobs = (
            await session.execute(select(Job).where(Job.id.in_(chunk)))
        ).scalars().all()
        for job in jobs:
            # Per-job isolation. Before this, one bad posting discarded every
            # score computed before it — a ten-minute refresh returning nothing,
            # with a single traceback to explain it.
            try:
                async with session.begin_nested():
                    await score_job(
                        session, job, user_id, mode=mode, facts=facts,
                        skills=skills, company_cache=company_cache,
                    )
                scored += 1
            except Exception as exc:
                failed.append(f"{job.id}: {type(exc).__name__}: {exc}")
        await session.commit()
        # Drop the batch from the identity map. Without this the session keeps a
        # reference to every posting it has ever loaded and batching buys nothing.
        session.expunge_all()

    return {
        "scored": scored,
        "failed": failed,
        "total": len(job_ids),
        "remaining": max(0, len(pending) - len(job_ids)),
        "mode": mode.value,
        "formula_version": "v3",
    }


async def latest_scores(
    session: AsyncSession,
    job_ids: list[str],
    *,
    user_id: str | None = None,
    mode: RankingMode = RankingMode.INTERNSHIP,
) -> dict[str, dict]:
    """The score per job for one owner and one ranking mode.

    Filtering on `ranking_mode` is not optional. Scores for different modes are
    different answers to different questions — `modes.py` weights company
    platform at 38% for internship and 18% for experienced — so mixing them
    silently ranks the pool by a formula the user did not ask for.

    This used to rely on "newest row wins" while the table appended a row per
    run, which happened to surface the mode you last recomputed. Now that
    rescoring UPDATEs in place, `created_at` stays pinned to when the row was
    first written, so without this filter the FIRST mode ever scored would win
    permanently and no recompute could dislodge it.
    """
    if not job_ids:
        return {}
    stmt = (
        select(ApplicationPriorityScore)
        .where(
            ApplicationPriorityScore.job_id.in_(job_ids),
            ApplicationPriorityScore.ranking_mode == mode.value,
        )
        .order_by(ApplicationPriorityScore.updated_at.desc())
    )
    if user_id is not None:
        stmt = stmt.where(ApplicationPriorityScore.user_id == user_id)
    rows = (await session.execute(stmt)).scalars().all()

    out: dict[str, dict] = {}
    for r in rows:
        if r.job_id in out:
            continue  # one row per (job, user, mode); this only guards a stale DB
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
            "opportunity_viability": r.opportunity_viability,
            "evidence_coverage": r.evidence_coverage,
            "application_priority": r.application_priority,
            "action_urgency": r.action_urgency,
            "application_effort_minutes": r.application_effort_minutes,
            "recommendation": r.recommendation,
            "interaction_rule": r.interaction_rule,
            "why": r.why,
            "why_not": r.why_not,
            "unknowns": r.unknowns,
        }
    return out
