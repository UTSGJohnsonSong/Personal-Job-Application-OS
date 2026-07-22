from __future__ import annotations

from datetime import UTC, datetime

from app.connectors._util import parse_dt, strip_html
from app.connectors.base import Connector, HttpLike, content_hash
from app.schemas.connector import ConnectorResult, RawJob, RawLocation, SourceConfig


class GenericAtsConnector(Connector):
    """Configurable connector for official career pages that expose a JSON feed.

    Field mapping is provided in ``source.config['mapping']`` so new official
    sources can be added WITHOUT code changes (see docs/CONNECTOR_INTERFACE.md).
    Example mapping:
        {"list_path": "results", "id": "reqId", "title": "name",
         "url": "applyUrl", "description": "jobDescription",
         "location": "primaryLocation", "posted": "postedDate"}
    """

    key = "generic_ats"
    source_priority = 2

    @staticmethod
    def _dig(obj, path: str):
        cur = obj
        for part in path.split("."):
            if isinstance(cur, dict):
                cur = cur.get(part)
            else:
                return None
        return cur

    async def fetch(self, source: SourceConfig, http: HttpLike, since=None) -> ConnectorResult:
        mapping = source.config.get("mapping", {})
        url = source.config["feed_url"]
        status, body, resp_headers = await http.get_json(url)
        if status == 304:
            return ConnectorResult(not_modified=True, fetched_at=datetime.now(UTC))

        list_path = mapping.get("list_path")
        items = self._dig(body, list_path) if list_path else body
        if not isinstance(items, list):
            items = []

        raw_jobs: list[RawJob] = []
        for it in items:
            title = self._dig(it, mapping.get("title", "title")) or ""
            desc_raw = self._dig(it, mapping.get("description", "description"))
            desc = strip_html(desc_raw) if desc_raw else None
            loc = self._dig(it, mapping.get("location", "location"))
            apply_url = self._dig(it, mapping.get("url", "url"))
            raw_jobs.append(
                RawJob(
                    source_job_id=str(self._dig(it, mapping.get("id", "id"))),
                    title=str(title).strip(),
                    description_text=desc,
                    locations=[RawLocation(raw_text=loc)] if loc else [],
                    official_source_url=apply_url,
                    canonical_application_url=apply_url,
                    source_posted_at=parse_dt(self._dig(it, mapping.get("posted", "posted"))),
                    source_status="open",
                    content_hash=content_hash(str(title), desc, loc),
                    raw=it,
                )
            )
        return ConnectorResult(
            raw_jobs=raw_jobs,
            etag=resp_headers.get("etag"),
            fetched_at=datetime.now(UTC),
        )
