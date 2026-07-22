from __future__ import annotations

import re

_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_COMPANY_SUFFIX = re.compile(
    r"\b(inc|llc|ltd|corp|corporation|co|gmbh|plc|sa|ag|pvt|technologies|technology|labs)\b"
)
_SENIORITY = re.compile(r"\b(sr|snr|senior|jr|junior|staff|principal|lead|i{1,3}|iv|v)\b")


def normalize_company(name: str | None) -> str:
    if not name:
        return ""
    s = name.strip().lower()
    s = _NON_ALNUM.sub(" ", s)
    s = _COMPANY_SUFFIX.sub(" ", s)
    return _WS.sub(" ", s).strip()


def normalize_title(title: str | None) -> str:
    if not title:
        return ""
    s = title.strip().lower()
    s = s.replace("&", " and ")
    s = _NON_ALNUM.sub(" ", s)
    return _WS.sub(" ", s).strip()


def title_core(title: str | None) -> str:
    """Title with seniority tokens removed — used as a soft dedup signal."""
    s = normalize_title(title)
    s = _SENIORITY.sub(" ", s)
    return _WS.sub(" ", s).strip()


def normalize_location(raw: str | None) -> dict:
    """Very light location parser: 'City, Region, Country' heuristics."""
    if not raw:
        return {"raw_text": None, "city": None, "region": None, "country": None}
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    city = parts[0] if parts else None
    region = parts[1] if len(parts) > 1 else None
    country = parts[-1] if len(parts) > 2 else (parts[1] if len(parts) == 2 else None)
    return {"raw_text": raw, "city": city, "region": region, "country": country}


def infer_remote_mode(text: str | None, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    if not text:
        return None
    t = text.lower()
    if "fully remote" in t or "100% remote" in t or "remote" in t:
        return "remote"
    if "hybrid" in t:
        return "hybrid"
    if "on-site" in t or "onsite" in t or "in office" in t:
        return "onsite"
    return None
