from __future__ import annotations

import hashlib
from typing import Protocol, runtime_checkable

from app.schemas.connector import ConnectorResult, SourceConfig


class ConnectorError(Exception):
    """Raised by connectors on failure. Ingestion isolates & records these so one
    failing source never blocks others (see docs/ARCHITECTURE.md)."""

    def __init__(self, message: str, *, stage: str = "fetch", retryable: bool = True):
        super().__init__(message)
        self.stage = stage
        self.retryable = retryable


@runtime_checkable
class HttpLike(Protocol):
    async def get_json(
        self, url: str, *, headers: dict | None = None
    ) -> tuple[int, dict | list, dict]: ...

    async def post_json(
        self, url: str, *, json: dict, headers: dict | None = None
    ) -> tuple[int, dict | list, dict]:
        """Required by boards whose public search endpoint is POST (Workday)."""
        ...

    async def get_text(
        self, url: str, *, headers: dict | None = None
    ) -> tuple[int, str, dict]:
        """Required by connectors that read public HTML (JSON-LD, sitemap)."""
        ...


@runtime_checkable
class Connector(Protocol):
    key: str
    source_priority: int

    async def fetch(
        self, source: SourceConfig, http: HttpLike, since=None
    ) -> ConnectorResult: ...


def content_hash(*parts: str | None) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8", "ignore"))
        h.update(b"\x00")
    return h.hexdigest()
