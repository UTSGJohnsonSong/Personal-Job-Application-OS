"""Builds the company-tier-centric inbox from stored scores and persists it.

Recommendations are computed here, on the server, and written to
recommended_application_sets(+_items) together with the inputs they were made
from. The UI then renders stored decisions instead of recomputing, so what the
user saw can always be reconstructed.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applications.recommendation import (
    ApplicationSet,
    build_application_set,
    redundancy_risk,
)
from app.company.portfolio import (
    CompanyEntry,
    RoleEntry,
    companies_requiring_action,
    global_priority_queue,
    group_by_tier,
    select_company_roles,
)
from app.company.profiles import resolve
from app.models.application import Application
from app.models.company_inbox import (
    CompanyRoleRanking,
    RecommendedApplicationSet,
    RecommendedApplicationSetItem,
    RoleSimilarityGroup,
)
from app.models.ranking_v2 import ApplicationPriorityScore
from app.models.sourcing import Company, Job, JobLocation
from app.models.user import User

CALCULATION_VERSION = "inbox-v1"
RANKING_FORMULA_VERSION = "v2"
SET_TTL_HOURS = 12

STUDENT_TERMS = re.compile(
    r"\b(intern|internship|co-?op|student|campus|new ?grad|early career|"
    r"rotational|apprentice)\b", re.I,
)
CANADA = re.compile(
    r"(toronto|canada|ontario|\bON\b|\bBC\b|\bAB\b|\bQC\b|vancouver|montr|ottawa|"
    r"waterloo|calgary|mississauga|scarborough|etobicoke|north york)", re.I,
)
GTA = re.compile(
    r"(toronto|mississauga|brampton|markham|vaughan|scarborough|etobicoke|"
    r"north york|richmond hill|oakville)", re.I,
)


async def _sole_user_id(session: AsyncSession) -> str | None:
    return (await session.execute(select(User.id).limit(1))).scalar_one_or_none()


async def load_companies(session: AsyncSession, user_id: str) -> list[CompanyEntry]:
    """Assemble CompanyEntry objects from stored jobs + v2 priority scores."""
    jobs = (
        await session.execute(select(Job).where(Job.deleted_at.is_(None)))
    ).scalars().all()
    companies = {
        c.id: c for c in (await session.execute(select(Company))).scalars().all()
    }

    # Latest score per job.
    scores: dict[str, ApplicationPriorityScore] = {}
    rows = (
        await session.execute(
            select(ApplicationPriorityScore)
            .where(ApplicationPriorityScore.user_id == user_id)
            .order_by(ApplicationPriorityScore.created_at.desc())
        )
    ).scalars().all()
    for s in rows:
        scores.setdefault(s.job_id, s)

    # Locations live in job_locations. Reading them from job.raw["locationsText"]
    # only ever worked for Workday, so every Ashby, Lever and Greenhouse posting
    # reported no location and no Canadian roles at all.
    locations: dict[str, str] = {}
    for loc in (
        await session.execute(select(JobLocation))
    ).scalars().all():
        if loc.raw_text and loc.job_id not in locations:
            locations[loc.job_id] = loc.raw_text

    applied_job_ids = {
        a.job_id for a in (
            await session.execute(
                select(Application).where(Application.user_id == user_id)
            )
        ).scalars().all()
        if a.submitted_at is not None or a.status not in ("discovered", "saved")
    }

    grouped: dict[str, CompanyEntry] = {}
    for job in jobs:
        score = scores.get(job.id)
        if score is None:
            continue  # unscored jobs cannot be organised or recommended yet
        cid = job.company_id or "unknown"
        entry = grouped.get(cid)
        if entry is None:
            comp = companies.get(cid)
            checked = job.last_verified_at or job.last_seen_at
            # The registry is the authority on tier. It is a dated, reviewed
            # assessment; the per-score company_tier is a by-product of however
            # much board evidence happened to be gathered, which is why every
            # company here read "D? (unrated)" while the registry had them
            # rated S through D.
            profile = resolve(comp.normalized_name if comp else "") or (
                resolve(comp.name) if comp else None
            )
            entry = CompanyEntry(
                company_id=cid,
                name=comp.name if comp else "Unknown company",
                tier=profile.personal_tier if profile else (score.company_tier or "D"),
                tier_display=(
                    profile.personal_tier if profile
                    else score.company_tier_display or score.company_tier or "D"
                ),
                provisional=(
                    False if profile else "?" in (score.company_tier_display or "")
                ),
                platform_value=(
                    profile.platform_score if profile else score.company_platform_value
                ),
                evidence_coverage=score.evidence_coverage,
                last_checked=checked.isoformat() if checked else None,
            )
            grouped[cid] = entry

        location = locations.get(job.id, "")
        entry.roles.append(RoleEntry(
            job_id=job.id,
            title=job.title,
            role_type=score.role_type or "unknown",
            role_band=score.role_band or "R3",
            application_priority=score.application_priority,
            eligibility=score.eligibility_gate,
            location=location,
            department=job.department,
            canonical_url=job.canonical_application_url,
            discovery_url=(job.raw or {}).get("discovery_url")
            if isinstance(job.raw, dict) else None,
            is_student_role=bool(STUDENT_TERMS.search(job.title or "")),
            already_applied=job.id in applied_job_ids,
            company_platform_value=score.company_platform_value,
            role_strategic_value=score.role_strategic_value,
            current_fit=score.current_candidate_fit,
            team_quality=score.team_project_quality,
            career_optionality=score.career_optionality,
            evidence_coverage=score.evidence_coverage,
            recommendation=score.recommendation or "",
            application_deadline=job.application_deadline,
        ))

    # Official source coverage per company.
    for entry in grouped.values():
        rel = entry.relevant_roles
        entry.official_source_coverage = (
            sum(1 for r in rel if r.is_official) / len(rel) if rel else 0.0
        )
    return list(grouped.values())


def company_stats(entry: CompanyEntry) -> dict:
    rel = entry.relevant_roles
    return {
        "total_open_roles": len(entry.roles),
        "canada_roles": sum(1 for r in entry.roles if CANADA.search(r.location or "")),
        "gta_roles": sum(1 for r in entry.roles if GTA.search(r.location or "")),
        "student_roles": len(entry.student_roles),
        "relevant_roles": len(rel),
        "submitted_applications": len(entry.applied_roles),
    }


async def persist_set(
    session: AsyncSession, user_id: str, result: ApplicationSet
) -> RecommendedApplicationSet:
    """Store a recommendation set with the inputs that produced it."""
    now = datetime.now(UTC)
    company = result.company

    record = RecommendedApplicationSet(
        user_id=user_id, company_id=company.company_id,
        calculation_version=CALCULATION_VERSION,
        company_tier=company.tier, company_tier_display=company.tier_display,
        provisional=company.provisional,
        recommended_limit=result.limit,
        recommended_count=len(result.recommended),
        excluded_count=len(result.excluded),
        already_applied_count=result.already_applied,
        over_limit=result.over_limit,
        evidence_snapshot={
            "platform_value": company.platform_value,
            "evidence_coverage": company.evidence_coverage,
            "official_source_coverage": company.official_source_coverage,
            **company_stats(company),
        },
        notes=result.notes,
        calculated_at=now,
        expires_at=now + timedelta(hours=SET_TTL_HOURS),
    )
    session.add(record)
    await session.flush()

    applied = company.applied_roles
    for rec in result.recommended:
        r = rec.role
        session.add(RecommendedApplicationSetItem(
            set_id=record.id, job_id=r.job_id, status="recommended",
            rank=rec.rank, title=r.title, role_family=r.family.value,
            role_band=r.role_band, similarity_group_key=r.similarity_group_id,
            application_priority=r.application_priority,
            company_platform_value=r.company_platform_value,
            role_strategic_value=r.role_strategic_value,
            current_candidate_fit=r.current_fit,
            team_project_quality=r.team_quality,
            career_optionality=r.career_optionality,
            evidence_coverage=r.evidence_coverage,
            reason=rec.reason, has_official_link=r.is_official,
        ))
    for exc in result.excluded:
        r = exc.role
        dup = any(redundancy_risk(r, a) >= 0.75 for a in applied)
        session.add(RecommendedApplicationSetItem(
            set_id=record.id, job_id=r.job_id, status="excluded",
            title=r.title, role_family=r.family.value, role_band=r.role_band,
            similarity_group_key=r.similarity_group_id,
            redundancy_risk=max((redundancy_risk(r, x.role)
                                 for x in result.recommended), default=0.0),
            application_priority=r.application_priority,
            reason=exc.reason, superseded_by=exc.superseded_by,
            duplicates_applied_role=dup, has_official_link=r.is_official,
        ))

    # Similarity groups
    seen_groups: dict[str, list[RoleEntry]] = {}
    for r in company.relevant_roles:
        if r.similarity_group_id:
            seen_groups.setdefault(r.similarity_group_id, []).append(r)
    for key, members in seen_groups.items():
        if len(members) < 2:
            continue
        best = max(members, key=lambda m: m.application_priority)
        session.add(RoleSimilarityGroup(
            company_id=company.company_id, group_key=key,
            representative_job_id=best.job_id, member_count=len(members),
            max_redundancy_risk=max(
                redundancy_risk(a, b) for a in members for b in members if a is not b
            ),
            rationale="near-identical titles in the same role family",
        ))
    return record


async def rebuild_inbox(session: AsyncSession, user_id: str) -> dict:
    """Recompute company organisation + recommendation sets and persist them."""
    companies = await load_companies(session, user_id)

    # Clear the previous generation so stale advice cannot linger.
    for model in (RecommendedApplicationSetItem, RecommendedApplicationSet,
                  RoleSimilarityGroup, CompanyRoleRanking):
        for row in (await session.execute(select(model))).scalars().all():
            await session.delete(row)
    await session.flush()

    sets = 0
    for entry in companies:
        result = build_application_set(entry)
        await persist_set(session, user_id, result)
        sets += 1

    # Materialise rankings: company-internal and global.
    now = datetime.now(UTC)
    queue = global_priority_queue(companies)
    global_rank = {r.job_id: i + 1 for i, (_c, r) in enumerate(queue)}
    for entry in companies:
        for i, role in enumerate(entry.ranked_roles(), start=1):
            session.add(CompanyRoleRanking(
                user_id=user_id, company_id=entry.company_id, job_id=role.job_id,
                company_internal_rank=i,
                global_rank=global_rank.get(role.job_id, 0),
                application_priority=role.application_priority,
                calculated_at=now,
            ))

    await session.commit()
    return {
        "companies": len(companies),
        "recommendation_sets": sets,
        "ranked_roles": len(queue),
        "calculation_version": CALCULATION_VERSION,
        "ranking_formula_version": RANKING_FORMULA_VERSION,
    }


def _selection_summary(c: CompanyEntry) -> dict:
    """Counts only, for the company-list card — full roles live on the
    company detail endpoint (app/api/routes/inbox.py `company_detail`)."""
    sel = select_company_roles(c)
    return {
        "recommended": len(sel.recommended),
        "strong_recommended": len(sel.strong_job_ids),
        "backup": len(sel.backup),
        "shortfall_message": sel.shortfall_message,
    }


def tier_view(companies: list[CompanyEntry]) -> list[dict]:
    """View 1 payload: companies grouped into tiers with their top roles."""
    out = []
    for group in group_by_tier(companies):
        out.append({
            "tier": group.tier,
            "company_count": group.company_count,
            "role_count": group.role_count,
            "companies": [
                {
                    "company_id": c.company_id,
                    "name": c.name,
                    "tier": c.tier,
                    "tier_display": c.tier_display,
                    "provisional": c.provisional,
                    "platform_value": round(c.platform_value, 1),
                    "evidence_coverage": round(c.evidence_coverage, 3),
                    "official_source_coverage": round(c.official_source_coverage, 3),
                    "last_synced_at": c.last_checked,
                    "high_potential_unrated": c.high_potential_unrated,
                    **company_stats(c),
                    "recommended_count": len(build_application_set(c).recommended),
                    "role_selection_summary": _selection_summary(c),
                    "top_roles": [
                        {
                            "job_id": r.job_id, "title": r.title,
                            "application_priority": round(r.application_priority, 1),
                            "role_band": r.role_band, "role_type": r.role_type,
                            "eligibility": r.eligibility,
                            "current_fit": round(r.current_fit, 1),
                            "role_strategic_value": round(r.role_strategic_value, 1),
                            "evidence_coverage": round(r.evidence_coverage, 3),
                            "is_official": r.is_official,
                            "apply_url": r.canonical_url,
                        }
                        for r in c.top_roles()
                    ],
                }
                for c in group.companies
            ],
        })
    return out


def global_view(companies: list[CompanyEntry], limit: int = 100) -> list[dict]:
    """View 2 payload: one queue across every tier, ordered by priority only."""
    return [
        {
            "global_rank": i + 1,
            "company_id": c.company_id,
            "company": c.name,
            "company_tier": c.tier_display,
            "company_platform_value": round(c.platform_value, 1),
            "job_id": r.job_id,
            "title": r.title,
            "role_band": r.role_band,
            "role_type": r.role_type,
            "eligibility": r.eligibility,
            "application_priority": round(r.application_priority, 1),
            "role_strategic_value": round(r.role_strategic_value, 1),
            "current_fit": round(r.current_fit, 1),
            "evidence_coverage": round(r.evidence_coverage, 3),
            "recommendation": r.recommendation,
            "is_official": r.is_official,
            "apply_url": r.canonical_url,
            "location": r.location,
            # Same opportunity, other places it is advertised. Collapsed rather
            # than listed as separate rows.
            "other_locations": r.other_locations,
        }
        for i, (c, r) in enumerate(global_priority_queue(companies, limit=limit))
    ]


def dashboard_metrics(companies: list[CompanyEntry]) -> dict:
    sets = {c.company_id: build_application_set(c) for c in companies}
    all_roles = [r for c in companies for r in c.relevant_roles]
    return {
        "s_tier_companies_monitored": sum(1 for c in companies if c.bucket == "S"),
        "a_tier_companies_monitored": sum(1 for c in companies if c.bucket == "A"),
        "official_source_coverage": round(
            sum(c.official_source_coverage for c in companies) / len(companies), 3
        ) if companies else 0.0,
        "companies_with_recommended_applications": sum(
            1 for s in sets.values() if s.recommended
        ),
        "high_priority_roles_across_tiers": sum(
            1 for r in all_roles if r.application_priority >= 80
        ),
        "high_potential_unrated_companies": sum(
            1 for c in companies if c.high_potential_unrated
        ),
        "companies_near_application_limit": sum(
            1 for s in sets.values() if s.over_limit
        ),
        "companies_requiring_action": len(companies_requiring_action(companies)),
        "total_companies": len(companies),
        "total_relevant_roles": len(all_roles),
    }
