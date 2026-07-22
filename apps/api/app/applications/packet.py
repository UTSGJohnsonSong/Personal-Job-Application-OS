from __future__ import annotations

import hashlib
import json


def packet_hash(payload: dict) -> str:
    """Deterministic hash of the exact material the user reviews and submits.

    Any change to resume choice, answers, or documents changes the hash, which
    invalidates a prior confirmation and forces re-confirmation.
    """
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_packet_snapshot(
    *,
    company: str,
    role: str,
    official_url: str | None,
    resume_version_id: str | None,
    answers: list[dict],
    documents: list[str],
    cover_letter: str | None,
) -> dict:
    """The immutable snapshot shown on the confirmation page (Level 3)."""
    return {
        "company": company,
        "role": role,
        "official_url": official_url,
        "resume_version_id": resume_version_id,
        "answers": sorted(answers, key=lambda a: a.get("question", "")),
        "documents": sorted(documents),
        "cover_letter": cover_letter,
    }
