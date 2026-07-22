"""Worker entrypoints. Runnable in-process (no broker) for local/dev use.

A production deployment wraps these in Dramatiq/Celery/RQ actors on a schedule
(see workers/README.md). All tasks are idempotent and failure-isolated.
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.connectors.http import HttpClient
from app.connectors.registry import get_connector
from app.core.logging import configure_logging, get_logger
from app.db.session import SessionLocal
from app.ingestion.sync import ingest_result
from app.models.ops import ConnectorFailure
from app.models.sourcing import JobSource, SourceSyncRun
from app.schemas.connector import SourceConfig

log = get_logger("workers")


async def sync_source(connector_key: str, board: str) -> dict:
    """Sync a single source. Idempotent per (source, source_job_id)."""
    async with SessionLocal() as session:
        source = (
            await session.execute(
                select(JobSource).where(
                    JobSource.connector_key == connector_key,
                    JobSource.external_id == board,
                )
            )
        ).scalar_one_or_none()
        if source is None:
            source = JobSource(
                connector_key=connector_key, external_id=board,
                display_name=f"{connector_key}:{board}",
            )
            session.add(source)
            await session.flush()

        run = SourceSyncRun(source_id=source.id, idempotency_key=f"{connector_key}:{board}",
                            status="running")
        session.add(run)
        connector = get_connector(connector_key)
        cfg = SourceConfig(
            connector_key=connector_key, external_id=board,
            display_name=source.display_name, etag=source.etag,
            last_modified=source.last_modified, config=source.config or {},
        )
        try:
            async with HttpClient() as http:
                result = await connector.fetch(cfg, http)
            stats = await ingest_result(session, source, result)
            run.status = "ok"
            run.jobs_seen = stats["seen"]
            run.jobs_new = stats["new"]
            run.jobs_updated = stats["updated"]
            await session.commit()
            log.info("sync %s:%s -> %s", connector_key, board, stats)
            return stats
        except Exception as exc:  # failure isolation
            run.status = "failed"
            run.error = str(exc)[:2000]
            session.add(ConnectorFailure(source_id=source.id, connector_key=connector_key,
                                         stage="fetch", error=str(exc)[:2000]))
            await session.commit()
            log.warning("sync failed %s:%s -> %s", connector_key, board, exc)
            return {"error": str(exc)}


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(prog="workers")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sync")
    p.add_argument("--connector", required=True)
    p.add_argument("--board", required=True)
    args = parser.parse_args()
    if args.cmd == "sync":
        print(asyncio.run(sync_source(args.connector, args.board)))


if __name__ == "__main__":
    main()
