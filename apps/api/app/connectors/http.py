from __future__ import annotations

import asyncio

import httpx

from app.connectors.base import ConnectorError
from app.core.config import get_settings


class HttpClient:
    """Polite async HTTP client: timeout, retry with exponential backoff.

    Rate limiting is applied per-source by the sync orchestrator; this client
    enforces per-request timeouts and bounded retries.
    """

    def __init__(self, *, timeout: float | None = None, max_retries: int = 3):
        s = get_settings()
        self._timeout = timeout or s.connector_http_timeout_seconds
        self._max_retries = max_retries
        self._headers = {"User-Agent": s.connector_user_agent}
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> HttpClient:
        self._client = httpx.AsyncClient(timeout=self._timeout, headers=self._headers)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()

    async def get_json(
        self, url: str, *, headers: dict | None = None
    ) -> tuple[int, dict | list, dict]:
        assert self._client is not None, "use inside 'async with HttpClient()'"
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                resp = await self._client.get(url, headers=headers)
                if resp.status_code == 304:
                    return 304, {}, dict(resp.headers)
                if resp.status_code >= 500:
                    raise ConnectorError(f"{url} -> {resp.status_code}", retryable=True)
                if resp.status_code == 429:
                    await asyncio.sleep(2 ** attempt)
                    continue
                if resp.status_code >= 400:
                    raise ConnectorError(f"{url} -> {resp.status_code}", retryable=False)
                return resp.status_code, resp.json(), dict(resp.headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                await asyncio.sleep(min(2 ** attempt, 8))
        raise ConnectorError(f"GET {url} failed after retries: {last_exc}", retryable=True)
