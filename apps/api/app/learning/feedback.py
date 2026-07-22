from __future__ import annotations

from collections import defaultdict

# Phase-1 learning: explainable rules + statistics over REAL outcomes, not clicks.
# Produces weight-adjustment SUGGESTIONS (never silent, always rollbackable).


def outcome_rates_by_key(events: list[dict], key: str) -> dict[str, dict[str, float]]:
    """Aggregate reply/interview/offer rates grouped by a dimension (e.g. source).

    events: [{key: <group>, "submitted": bool, "reply": bool, "interview": bool,
             "offer": bool}, ...]
    """
    agg: dict[str, dict[str, int]] = defaultdict(
        lambda: {"submitted": 0, "reply": 0, "interview": 0, "offer": 0}
    )
    for e in events:
        g = str(e.get(key, "unknown"))
        for m in ("submitted", "reply", "interview", "offer"):
            if e.get(m):
                agg[g][m] += 1

    out: dict[str, dict[str, float]] = {}
    for g, c in agg.items():
        sub = c["submitted"] or 1
        out[g] = {
            "n": float(c["submitted"]),
            "reply_rate": c["reply"] / sub,
            "interview_rate": c["interview"] / sub,
            "offer_rate": c["offer"] / sub,
        }
    return out


def suggest_weight_adjustments(
    current_weights: dict[str, float],
    dimension_outcome_corr: dict[str, float],
    *,
    max_step: float = 0.2,
    min_samples: dict[str, int] | None = None,
) -> list[dict]:
    """Suggest small, bounded, explainable weight nudges from outcome correlation.

    dimension_outcome_corr: dimension -> correlation with positive outcome in [-1,1].
    Returns a list of suggestions; nothing is applied automatically.
    """
    suggestions: list[dict] = []
    for dim, corr in dimension_outcome_corr.items():
        if dim not in current_weights:
            continue
        delta = round(max(-max_step, min(max_step, corr * max_step)), 3)
        if abs(delta) < 0.02:
            continue
        suggestions.append(
            {
                "dimension": dim,
                "before": current_weights[dim],
                "after": round(current_weights[dim] + delta, 3),
                "reason": (
                    f"dimension '{dim}' correlates {corr:+.2f} with positive outcomes; "
                    f"nudging weight by {delta:+.3f}"
                ),
            }
        )
    return suggestions
