"""The application pool — one list, grouped by tier.

Replaces the three separate ranking views. Those exposed the scoring machinery
as its own destination, which put the method in front of the work; the pool puts
companies and their open roles in front, and keeps the reasoning available on
the company page for when it is actually wanted.

Shape:

    tier -> companies (best first) -> that company's top roles

A refresh is a long, network-bound job, so it runs in the background with
progress that the UI can poll. Progress is reported from work actually
completed, never from a timer.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.company.access import LocationClass, classify_location, preferred_location
from app.company.portfolio import CompanyEntry, RoleEntry, select_company_roles
from app.company.profiles import ALL_PROFILES, BY_KEY, resolve
from app.company.sources import ALL_SOURCES, SourceStatus
from app.models.ranking_v2 import ApplicationPriorityScore
from app.models.sourcing import Company, Job, JobLocation
from app.ranking.modes import RankingMode

TIER_ORDER = ("S", "A", "B", "C", "D")

# How many roles a card shows before the company has to be expanded. The spec
# is "at least three"; S and A get more because that is where attention should
# go, and the full list is always one click away.
CARD_ROLES = {"S": 5, "A": 4, "B": 3, "C": 3, "D": 3}


def _canada(loc: str) -> bool:
    return classify_location(loc) in (
        LocationClass.CANADA_EXPLICIT, LocationClass.CANADA_REMOTE)


async def _live_roles(session: AsyncSession, user_id: str) -> dict[str, list[dict]]:
    """Open roles per registry key, best first, with everything a card needs."""
    jobs = (
        await session.execute(select(Job).where(Job.deleted_at.is_(None)))
    ).scalars().all()
    companies = {
        c.id: c for c in (await session.execute(select(Company))).scalars().all()
    }
    # Same location choice the eligibility gate made. Taking whichever row came
    # back first showed "Dubai · eligible" on a Toronto-and-Dubai requisition —
    # the card contradicting the verdict beside it.
    raw_by_job: dict[str, list[str | None]] = {}
    for loc in (await session.execute(select(JobLocation))).scalars().all():
        raw_by_job.setdefault(loc.job_id, []).append(loc.raw_text)
    locations: dict[str, str] = {}
    for job_id, texts in raw_by_job.items():
        chosen = preferred_location(texts)
        if chosen:
            locations[job_id] = chosen

    # Filtered by ranking_mode: internship weights company platform at 38%,
    # experienced at 18%. Mixing them ranks the pool by a formula nobody asked
    # for. `created_at` is no longer a usable recency signal either — the upsert
    # updates rows in place, so it is pinned to first write.
    scores: dict[str, ApplicationPriorityScore] = {}
    for s in (
        await session.execute(
            select(ApplicationPriorityScore)
            .where(
                ApplicationPriorityScore.user_id == user_id,
                ApplicationPriorityScore.ranking_mode == RankingMode.INTERNSHIP.value,
            )
            .order_by(ApplicationPriorityScore.updated_at.desc())
        )
    ).scalars().all():
        scores.setdefault(s.job_id, s)

    out: dict[str, list[dict]] = {}
    for job in jobs:
        comp = companies.get(job.company_id or "")
        if comp is None:
            continue
        profile = resolve(comp.normalized_name) or resolve(comp.name)
        if profile is None:
            continue
        score = scores.get(job.id)
        location = locations.get(job.id, "")
        out.setdefault(profile.key, []).append({
            "job_id": job.id,
            "title": job.title,
            "location": location,
            "in_canada": _canada(location),
            "department": job.department,
            "apply_url": job.canonical_application_url,
            "posted_at": job.source_posted_at.isoformat() if job.source_posted_at else None,
            "first_seen_at": job.first_seen_at.isoformat() if job.first_seen_at else None,
            "deadline": (job.application_deadline.isoformat()
                         if job.application_deadline else None),
            "freshness": round(job.freshness_score, 2),
            "priority": round(score.application_priority, 1) if score else None,
            "eligibility": score.eligibility_gate if score else "UNSCORED",
            "role_band": score.role_band if score else None,
            "role_type": score.role_type if score else None,
        })

    for roles in out.values():
        # Eligible first, then priority. A role he cannot apply to should never
        # occupy one of the three slots on a card.
        rank = {"PASS": 0, "REVIEW": 1, "UNSCORED": 2, "FAIL": 3}
        roles.sort(key=lambda r: (rank.get(r["eligibility"], 3), -(r["priority"] or 0)))
        for i, r in enumerate(roles, 1):
            r["rank"] = i
    return out


async def build_pool(session: AsyncSession, user_id: str) -> dict:
    live = await _live_roles(session, user_id)
    source_status = {s.company_key: s for s in ALL_SOURCES}

    groups: list[dict] = []
    for tier in TIER_ORDER:
        members = [p for p in ALL_PROFILES if p.personal_tier == tier]
        cards: list[dict] = []
        for p in members:
            roles = live.get(p.key, [])
            open_now = [r for r in roles if r["eligibility"] != "FAIL"]
            src = source_status.get(p.key)
            cards.append({
                "key": p.key,
                "name": p.name,
                "score": round(p.personal_score, 1),
                "value": round(p.value_score, 1),
                "access": round(p.access_score, 1),
                "platform_tier": p.platform_tier,
                "posture": p.posture.value,
                "safety_net": p.safety_net,
                "why": p.why,
                "tags": list(p.tags),
                "source_status": src.status.value if src else (
                    "verified" if p.boards else "searching"),
                "careers_url": src.careers_url if src else None,
                "total_roles": len(roles),
                "open_roles": len(open_now),
                "canada_roles": sum(1 for r in roles if r["in_canada"]),
                # Top roles shown on the card; the rest live on the company page.
                "top_roles": open_now[:CARD_ROLES.get(tier, 3)],
                "has_more": len(open_now) > CARD_ROLES.get(tier, 3),
            })
        # Companies with live roles lead, then by score. A high-scoring company
        # with nothing open should not sit above one you can actually apply to.
        cards.sort(key=lambda c: (0 if c["open_roles"] else 1,
                                  -float(c["score"])))
        if cards:
            groups.append({
                "tier": tier,
                "company_count": len(cards),
                "open_roles": sum(c["open_roles"] for c in cards),
                "companies": cards,
            })
    return {
        "groups": groups,
        "total_companies": len(ALL_PROFILES),
        "total_open_roles": sum(g["open_roles"] for g in groups),
        "last_refreshed": REFRESH.finished_at,
    }


def _role_selection_dict(profile, roles: list[dict]) -> dict:
    """Recommended/Backup split (2026-07-24) for this company's role dicts.

    Reuses app/company/portfolio.py's select_company_roles rather than
    reimplementing the threshold/backfill/dedup logic a second time —
    builds throwaway RoleEntry objects just to run it, since this page's
    roles are plain dicts (see _live_roles), not RoleEntry instances.
    """
    entries = [
        RoleEntry(
            job_id=r["job_id"], title=r["title"],
            role_type=r["role_type"] or "unknown",
            role_band=r["role_band"] or "R3",
            application_priority=r["priority"] or 0.0,
            eligibility=r["eligibility"],
            application_deadline=(
                datetime.fromisoformat(r["deadline"]) if r["deadline"] else None
            ),
        )
        for r in roles
    ]
    entry = CompanyEntry(
        company_id=profile.key, name=profile.name, tier=profile.personal_tier,
        tier_display=profile.personal_tier, provisional=False,
        platform_value=profile.platform_score, evidence_coverage=1.0,
        roles=entries,
    )
    sel = select_company_roles(entry)
    return {
        "recommended_job_ids": [r.job_id for r in sel.recommended],
        "strong_job_ids": list(sel.strong_job_ids),
        "backup_job_ids": [r.job_id for r in sel.backup],
        "shortfall_message": sel.shortfall_message,
    }


async def company_detail(session: AsyncSession, user_id: str, key: str) -> dict | None:
    profile = BY_KEY.get(key)
    if profile is None:
        return None
    live = await _live_roles(session, user_id)
    roles = live.get(key, [])
    src = next((s for s in ALL_SOURCES if s.company_key == key), None)
    return {
        "key": profile.key,
        "name": profile.name,
        "tier": profile.personal_tier,
        "platform_tier": profile.platform_tier,
        "score": round(profile.personal_score, 1),
        "value": round(profile.value_score, 1),
        "access": round(profile.access_score, 1),
        "platform_score": round(profile.platform_score, 1),
        "posture": profile.posture.value,
        "why": profile.why,
        "adjustment_reason": profile.adjustment_reason,
        "tags": list(profile.tags),
        "safety_net": profile.safety_net,
        "role_floor": profile.role_floor,
        "worth_taking_if_offered": profile.worth_taking_if_offered,
        "assessed_on": profile.assessed_on,
        "valid_until": profile.valid_until,
        "inputs": {
            "brand_ca": profile.brand_ca, "brand_us": profile.brand_us,
            "brand_cn": profile.brand_cn, "tech": profile.tech,
            "depth": profile.depth, "role": profile.role,
            "domain": profile.domain, "founder": profile.founder,
            "program": profile.program,
        },
        "source": {
            "status": src.status.value if src else (
                "verified" if profile.boards else "searching"),
            "careers_url": src.careers_url if src else None,
            "connector": src.connector if src else (
                profile.boards[0][0] if profile.boards else None),
            "note": src.note if src else None,
            "probed_on": src.probed_on if src else None,
        },
        "roles": roles,
        "role_selection": _role_selection_dict(profile, roles),
        "counts": {
            "total": len(roles),
            "open": sum(1 for r in roles if r["eligibility"] != "FAIL"),
            "canada": sum(1 for r in roles if r["in_canada"]),
            "eligible": sum(1 for r in roles if r["eligibility"] == "PASS"),
        },
    }


# ---------------------------------------------------------------------------
# Refresh, with progress the UI can actually show.
# ---------------------------------------------------------------------------
@dataclass
class RefreshState:
    running: bool = False
    total: int = 0
    done: int = 0
    current: str = ""
    stage: str = ""
    started_at: float = 0.0
    finished_at: str | None = None
    error: str | None = None
    new_jobs: int = 0
    seconds_per_unit: float = 6.0  # measured, seeded from observed sync times
    log: list[str] = field(default_factory=list)

    @property
    def percent(self) -> int:
        return int(100 * self.done / self.total) if self.total else 0

    @property
    def eta_seconds(self) -> int:
        """Estimated from work already completed, not from a fixed timer."""
        if not self.running or not self.total:
            return 0
        remaining = max(0, self.total - self.done)
        if self.done:
            rate = (time.monotonic() - self.started_at) / self.done
        else:
            rate = self.seconds_per_unit
        return int(remaining * rate)

    def snapshot(self) -> dict:
        return {
            "running": self.running,
            "total": self.total,
            "done": self.done,
            "percent": self.percent,
            "current": self.current,
            "stage": self.stage,
            "eta_seconds": self.eta_seconds,
            "elapsed_seconds": (
                int(time.monotonic() - self.started_at) if self.started_at else 0),
            "finished_at": self.finished_at,
            "new_jobs": self.new_jobs,
            "error": self.error,
            "log": self.log[-12:],
        }


REFRESH = RefreshState()


def estimate_refresh() -> dict:
    """What the user is about to wait for, before they commit to waiting."""
    syncable = [s for s in ALL_SOURCES
                if s.status in (SourceStatus.VERIFIED, SourceStatus.PARTIAL)]
    # Sources, then scoring, then the inbox rebuild.
    units = len(syncable) + 2
    return {
        "sources": len(syncable),
        "units": units,
        "estimated_seconds": int(units * REFRESH.seconds_per_unit),
    }


async def run_refresh(session_factory, user_id: str) -> None:
    """Sync every verified source, rescore, rebuild. Progress is reported per
    completed unit of work so the bar never advances on a lie."""
    from app.connectors.http import HttpClient
    from app.connectors.registry import get_connector
    from app.ingestion.sync import ingest_result
    from app.models.sourcing import JobSource
    from app.schemas.connector import SourceConfig
    from app.services.inbox import rebuild_inbox
    from app.services.scoring_v2 import score_all_jobs

    syncable = [s for s in ALL_SOURCES
                if s.status in (SourceStatus.VERIFIED, SourceStatus.PARTIAL)]
    REFRESH.running = True
    REFRESH.total = len(syncable) + 2
    REFRESH.done = 0
    REFRESH.new_jobs = 0
    REFRESH.error = None
    REFRESH.log = []
    REFRESH.started_at = time.monotonic()
    REFRESH.stage = "sources"

    try:
        async with HttpClient(max_retries=2, timeout=45) as http:
            for src in syncable:
                profile = BY_KEY[src.company_key]
                REFRESH.current = profile.name
                try:
                    connector = get_connector(src.connector or "")
                    async with session_factory() as session:
                        source = (await session.execute(
                            select(JobSource).where(
                                JobSource.connector_key == src.connector,
                                JobSource.external_id == src.external_id)
                        )).scalar_one_or_none()
                        if source is None:
                            REFRESH.log.append(f"{profile.name}: not registered, skipped")
                            REFRESH.done += 1
                            continue
                        result = await connector.fetch(SourceConfig(
                            connector_key=src.connector or "",
                            external_id=src.external_id or "",
                            display_name=profile.name,
                            config=dict(src.config)), http)
                        stats = await ingest_result(session, source, result)
                        await session.commit()
                    REFRESH.new_jobs += stats.get("new", 0)
                    REFRESH.log.append(
                        f"{profile.name}: {len(result.raw_jobs)} seen, "
                        f"{stats.get('new', 0)} new")
                except Exception as exc:  # one bad board never stops the run
                    REFRESH.log.append(f"{profile.name}: FAILED {type(exc).__name__}")
                REFRESH.done += 1

        REFRESH.stage = "scoring"
        REFRESH.current = "recomputing priorities"
        async with session_factory() as session:
            await score_all_jobs(session, user_id)
        REFRESH.done += 1

        REFRESH.stage = "rebuilding"
        REFRESH.current = "rebuilding recommendations"
        async with session_factory() as session:
            await rebuild_inbox(session, user_id)
            await session.commit()
        REFRESH.done += 1

        REFRESH.finished_at = datetime.now(UTC).isoformat()
        # Learn the real rate so the next estimate is honest.
        if REFRESH.total:
            REFRESH.seconds_per_unit = (
                time.monotonic() - REFRESH.started_at) / REFRESH.total
    except Exception as exc:
        REFRESH.error = f"{type(exc).__name__}: {exc}"
    finally:
        REFRESH.running = False
        REFRESH.current = ""
        REFRESH.stage = "done" if not REFRESH.error else "failed"


def start_refresh(session_factory, user_id: str) -> dict:
    if REFRESH.running:
        return {"started": False, "reason": "already running", **REFRESH.snapshot()}
    # Kept as a module-level reference so the task is not garbage collected
    # mid-run, which would silently abandon a refresh the user is watching.
    global _TASK
    _TASK = asyncio.create_task(run_refresh(session_factory, user_id))
    return {"started": True, **estimate_refresh()}


_TASK: asyncio.Task | None = None
