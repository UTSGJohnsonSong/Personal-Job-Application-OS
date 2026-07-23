"""Sync real postings from every VERIFIED source in the registry.

Step 8 of the pipeline. Until now the database held two fictional demo rows, so
every page except the registry was empty; this is what makes the rest of the
site show something true.

Only sources marked VERIFIED or PARTIAL in `app/company/sources.py` are synced —
those are the ones actually probed against a live board. MANUAL_ONLY companies
are deliberately skipped here: they are not missing, they belong to the manual
application queue, and inventing a feed for them would be worse than having none.

Usage:  python scripts/sync_verified.py [--purge-demo]
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import delete, select

from app.company.profiles import BY_KEY
from app.company.sources import ALL_SOURCES, SourceStatus
from app.connectors.http import HttpClient
from app.connectors.registry import get_connector
from app.db.session import SessionLocal
from app.ingestion.sync import ingest_result
from app.models.sourcing import Company, Job, JobSnapshot, JobSource
from app.schemas.connector import SourceConfig


async def _company_for(session, key: str) -> Company:
    """One Company row per registry entry, matched on the registry key."""
    profile = BY_KEY[key]
    existing = (await session.execute(
        select(Company).where(Company.normalized_name == key)
    )).scalar_one_or_none()
    if existing:
        existing.name = profile.name
        return existing
    company = Company(name=profile.name, normalized_name=key)
    session.add(company)
    await session.flush()
    return company


async def _source_for(session, src, company: Company) -> JobSource:
    existing = (await session.execute(
        select(JobSource).where(
            JobSource.connector_key == src.connector,
            JobSource.external_id == src.external_id,
        )
    )).scalar_one_or_none()
    if existing:
        existing.company_id = company.id
        existing.config = dict(src.config)
        existing.enabled = True
        return existing
    source = JobSource(
        connector_key=src.connector,
        external_id=src.external_id,
        display_name=company.name,
        company_id=company.id,
        config=dict(src.config),
        enabled=True,
    )
    session.add(source)
    await session.flush()
    return source


async def purge_demo_data() -> int:
    """Remove the fictional seed rows so nothing on the site is invented."""
    async with SessionLocal() as session:
        demo = (await session.execute(
            select(Company).where(Company.normalized_name.like("%example%"))
        )).scalars().all()
        if not demo:
            return 0
        ids = [c.id for c in demo]
        jobs = (await session.execute(
            select(Job.id).where(Job.company_id.in_(ids))
        )).scalars().all()
        if jobs:
            await session.execute(delete(JobSnapshot).where(JobSnapshot.job_id.in_(jobs)))
            await session.execute(delete(Job).where(Job.id.in_(jobs)))
        await session.execute(delete(JobSource).where(JobSource.company_id.in_(ids)))
        await session.execute(delete(Company).where(Company.id.in_(ids)))
        await session.commit()
        return len(jobs)


async def main() -> None:
    if "--purge-demo" in sys.argv:
        removed = await purge_demo_data()
        print(f"purged {removed} fictional demo job(s)\n")

    syncable = [s for s in ALL_SOURCES
                if s.status in (SourceStatus.VERIFIED, SourceStatus.PARTIAL)]
    print(f"syncing {len(syncable)} verified source(s)\n")
    print(f"{'COMPANY':<20}{'CONNECTOR':>16}{'NEW':>6}{'UPDATED':>9}{'TOTAL':>7}")
    print("-" * 58)

    totals = {"new": 0, "updated": 0, "seen": 0}
    async with HttpClient(max_retries=2, timeout=45) as http:
        for src in syncable:
            profile = BY_KEY[src.company_key]
            try:
                connector = get_connector(src.connector)
            except KeyError:
                print(f"{profile.name[:19]:<20}{src.connector:>16}   no connector")
                continue

            async with SessionLocal() as session:
                company = await _company_for(session, src.company_key)
                source = await _source_for(session, src, company)
                cfg = SourceConfig(
                    connector_key=src.connector,
                    external_id=src.external_id,
                    display_name=company.name,
                    config=dict(src.config),
                )
                try:
                    result = await connector.fetch(cfg, http)
                except Exception as exc:
                    print(f"{profile.name[:19]:<20}{src.connector:>16}"
                          f"   FAILED {type(exc).__name__}")
                    continue

                # Every posting inherits the company the source belongs to, so
                # the tier layer can join without guessing from a job title.
                for raw in result.raw_jobs:
                    raw.company_name = company.name
                stats = await ingest_result(session, source, result)
                await session.commit()

            new = stats.get("new", 0)
            upd = stats.get("updated", 0)
            totals["new"] += new
            totals["updated"] += upd
            totals["seen"] += len(result.raw_jobs)
            print(f"{profile.name[:19]:<20}{src.connector:>16}{new:>6}{upd:>9}"
                  f"{len(result.raw_jobs):>7}")

    print(f"\n{totals['seen']} postings seen, {totals['new']} new, "
          f"{totals['updated']} updated")

    async with SessionLocal() as session:
        jobs = (await session.execute(select(Job))).scalars().all()
        companies = (await session.execute(select(Company))).scalars().all()
    print(f"database now holds {len(jobs)} jobs across {len(companies)} companies")


if __name__ == "__main__":
    asyncio.run(main())
