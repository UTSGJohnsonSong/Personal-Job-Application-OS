from __future__ import annotations

import re
from datetime import UTC, datetime

# Human date formats seen on career sites, e.g. SuccessFactors "Jul 22, 2026".
_HUMAN_DATE_FORMATS = ("%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%Y/%m/%d", "%m/%d/%Y")


def parse_dt(value) -> datetime | None:
    """Parse ISO-8601, epoch (s/ms) or common human dates into aware UTC."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Lever uses epoch milliseconds.
        ts = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(ts, tz=UTC)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        s = s.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            pass
        for fmt in _HUMAN_DATE_FORMATS:
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=UTC)
            except ValueError:
                continue
        return None
    return None


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")


def strip_html(html: str | None) -> str:
    if not html:
        return ""
    text = _TAG.sub(" ", html)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
    )
    lines = [_WS.sub(" ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)
