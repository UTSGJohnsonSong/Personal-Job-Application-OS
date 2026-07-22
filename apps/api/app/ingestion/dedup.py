from __future__ import annotations

from dataclasses import dataclass, field

from app.ingestion.normalize import normalize_company, normalize_location, title_core


@dataclass
class DedupKey:
    """Signals evaluated in priority order (docs/DATA_MODEL.md / product spec §17)."""

    connector_key: str | None = None
    source_job_id: str | None = None
    canonical_url: str | None = None
    requisition_id: str | None = None
    company_norm: str | None = None
    title_core: str | None = None
    location_key: str | None = None
    content_hash: str | None = None
    embedding: list[float] | None = field(default=None)


def build_key(raw, *, company_name: str | None = None) -> DedupKey:
    loc = raw.locations[0].raw_text if raw.locations else None
    loc_norm = normalize_location(loc)
    return DedupKey(
        source_job_id=raw.source_job_id,
        canonical_url=raw.canonical_application_url,
        company_norm=normalize_company(company_name or raw.company_name),
        title_core=title_core(raw.title),
        location_key=(loc_norm.get("city") or "").lower() or None,
        content_hash=raw.content_hash,
    )


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def is_duplicate(a: DedupKey, b: DedupKey, *, embed_threshold: float = 0.93) -> tuple[bool, str]:
    """Returns (duplicate?, reason). Ladder: exact ids -> url -> req -> norm -> hash -> embed."""
    if (
        a.connector_key
        and a.connector_key == b.connector_key
        and a.source_job_id == b.source_job_id
    ):
        return True, "same_source_job_id"
    if a.canonical_url and a.canonical_url == b.canonical_url:
        return True, "same_canonical_url"
    if (
        a.requisition_id
        and a.requisition_id == b.requisition_id
        and a.company_norm == b.company_norm
    ):
        return True, "same_requisition"
    if (
        a.company_norm
        and a.company_norm == b.company_norm
        and a.title_core == b.title_core
        and (a.location_key or None) == (b.location_key or None)
    ):
        return True, "same_company_title_location"
    if a.content_hash and a.content_hash == b.content_hash:
        return True, "same_content_hash"
    if a.embedding and b.embedding and _cosine(a.embedding, b.embedding) >= embed_threshold:
        return True, "embedding_similarity"
    return False, ""
