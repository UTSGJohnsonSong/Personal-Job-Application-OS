from __future__ import annotations

import hmac

from fastapi import Header, HTTPException

from app.core.config import get_settings


async def require_token(authorization: str | None = Header(default=None)) -> None:
    """Single-principal bearer-token gate.

    This instance has exactly one human owner (see docs/DECISIONS.md D7), so a
    single high-entropy token is the whole authz model. It protects the API from
    the open internet and is also how the MCP server authenticates.

    Constant-time compare avoids leaking the token via timing.
    """
    settings = get_settings()
    expected = settings.api_token.strip()

    # No token configured => the API is unprotected. Refuse rather than silently
    # serving personal data to anyone who finds the URL.
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="API_TOKEN is not configured; refusing to serve protected data.",
        )

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")

    provided = authorization[7:].strip()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="invalid token")
