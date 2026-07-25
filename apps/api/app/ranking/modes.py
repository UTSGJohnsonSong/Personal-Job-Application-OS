"""Ranking modes and their weight profiles (versioned, configurable).

Six weighted dimensions, each meant to answer ONE question with no overlap:

  company_platform_value  — is this employer worth having on a resume?
  role_strategic_value    — is THIS posting's direction/depth on-target?
  team_project_quality    — what would he actually be doing day to day?
  current_candidate_fit   — does he already have the skills this JD wants?
  career_optionality      — what does finishing this open up next?
  opportunity_viability    — is this a real, live, currently-applicable posting?

Explicitly NOT weighted dimensions (2025-07-24 redesign, user-specified):
  eligibility    — a gate (app/ranking/gate.py), never a score contribution.
  action_urgency — when to act, not whether the role is good. A job with a
                   deadline in 2 days is not a BETTER job than one with no
                   deadline; it is one that needs handling sooner. Mixing
                   the two used to give a flat +3 to any job closing within
                   72h, which rewarded urgency as if it were quality.
  application_effort — same failure mode: an easy 1-click application isn't
                   a better job than one requiring an essay, it's just
                   quicker to knock out. Feeds day-planning, not priority.
  evidence_coverage — how much of the above we could actually verify. Never
                   converted into extra points either direction; each
                   dimension already shrinks its own score toward a neutral
                   prior when coverage is thin (see ScoreWithCoverage).

No tier bonus or priority floor is applied on top of the six weights either.
Company standing is captured ONCE, at 38%, in company_platform_value. An
earlier version also added a Tier x Role bonus and a hard floor on top of
that — which the company-tier bridge (2026-07-24) would have made the floor
actually fire for the first time, quietly re-inflating exactly the
double-counting this redesign removes. Visibility for a strong company with
a thin-looking posting is handled at the recommendation/backfill layer
(app/services/inbox.py), not by lying about the posting's own score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class RankingMode(StrEnum):
    INTERNSHIP = "internship"
    NEW_GRAD = "new_grad"
    EXPERIENCED = "experienced"


@dataclass
class ModeWeights:
    company_platform_value: float
    role_strategic_value: float
    team_project_quality: float
    current_candidate_fit: float
    career_optionality: float
    opportunity_viability: float

    def as_dict(self) -> dict[str, float]:
        return {
            "company_platform_value": self.company_platform_value,
            "role_strategic_value": self.role_strategic_value,
            "team_project_quality": self.team_project_quality,
            "current_candidate_fit": self.current_candidate_fit,
            "career_optionality": self.career_optionality,
            "opportunity_viability": self.opportunity_viability,
        }

    def total(self) -> float:
        return sum(self.as_dict().values())


DEFAULT_WEIGHTS: dict[RankingMode, ModeWeights] = {
    # Platform dominates at internship stage. User-specified 2026-07-24.
    RankingMode.INTERNSHIP: ModeWeights(0.38, 0.20, 0.15, 0.11, 0.10, 0.06),
    # Extrapolated from the internship weights, same direction as the old
    # profile (company matters less, team/fit matter more) — not explicitly
    # specified, revisit when new-grad mode is actually used.
    RankingMode.NEW_GRAD: ModeWeights(0.30, 0.22, 0.18, 0.17, 0.08, 0.05),
    # Manager, responsibilities, comp, stability dominate. Same caveat as
    # new-grad: extrapolated, not user-specified.
    RankingMode.EXPERIENCED: ModeWeights(0.18, 0.22, 0.24, 0.20, 0.10, 0.06),
}


@dataclass
class RankingProfile:
    """User-configurable, versioned ranking profile.

    Preferences live here rather than as hard-coded conditions in business logic.
    Changing this requires explicit user confirmation.
    """

    mode: RankingMode = RankingMode.INTERNSHIP
    weights: ModeWeights = field(
        default_factory=lambda: DEFAULT_WEIGHTS[RankingMode.INTERNSHIP]
    )
    version_label: str = "v3-internship-default"
    neutral_prior: float = 0.5

    @classmethod
    def for_mode(cls, mode: RankingMode) -> RankingProfile:
        return cls(
            mode=mode,
            weights=DEFAULT_WEIGHTS[mode],
            version_label=f"v3-{mode.value}-default",
        )
