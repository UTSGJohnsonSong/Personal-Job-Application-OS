from __future__ import annotations

import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


class FakeHttp:
    """Deterministic HTTP stand-in for connector contract tests (no network).

    Maps a URL substring -> fixture file, so connectors are exercised exactly as
    in production but against recorded payloads.
    """

    def __init__(self, routes: dict[str, str], *, status: int = 200):
        self._routes = routes
        self._status = status

    async def get_json(self, url: str, *, headers: dict | None = None):
        for needle, fixture in self._routes.items():
            if needle in url:
                data = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
                return self._status, data, {"etag": "W/\"fixture\""}
        raise AssertionError(f"no fixture route for {url}")
