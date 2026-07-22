from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta


def _decay(age_seconds: float, half_life_days: float) -> float:
    if age_seconds <= 0:
        return 1.0
    hl = half_life_days * 86400
    return math.exp(-math.log(2) * age_seconds / hl)


def compute_freshness(
    *,
    now: datetime | None = None,
    source_posted_at: datetime | None,
    last_verified_at: datetime | None,
    application_deadline: datetime | None,
    source_status: str = "open",
) -> float:
    """Deterministic freshness score in [0,1]. See docs/FRESHNESS_STRATEGY.md."""
    now = now or datetime.now(UTC)
    if source_status in {"closed", "removed"}:
        return 0.0

    verified_age = (now - last_verified_at).total_seconds() if last_verified_at else 3 * 86400
    posted_age = (now - source_posted_at).total_seconds() if source_posted_at else 14 * 86400

    recency = _decay(verified_age, half_life_days=3)
    posting = _decay(posted_age, half_life_days=21)

    boost = 0.0
    if application_deadline:
        remaining = (application_deadline - now).total_seconds()
        if 0 <= remaining <= 72 * 3600:
            boost = 0.15

    score = 0.55 * recency + 0.45 * posting + boost
    return max(0.0, min(1.0, score))


def next_verification_delay(
    *, freshness: float, application_deadline: datetime | None, is_target: bool
) -> timedelta:
    """How long until this job should be re-verified (idempotent scheduler)."""
    now = datetime.now(UTC)
    if application_deadline and (application_deadline - now) <= timedelta(hours=72):
        return timedelta(hours=6)
    if is_target:
        return timedelta(hours=12)
    if freshness < 0.2:
        return timedelta(days=3)
    return timedelta(days=1)
