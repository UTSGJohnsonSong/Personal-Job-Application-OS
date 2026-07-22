"""Ranking modes and their weight profiles (versioned, configurable).

The 50% company weight is specific to Internship Mode and must NOT be reused for
other career stages (docs/INTERNSHIP_RANKING.md).
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
    opportunity_estimate: float
    freshness_and_effort: float

    def as_dict(self) -> dict[str, float]:
        return {
            "company_platform_value": self.company_platform_value,
            "role_strategic_value": self.role_strategic_value,
            "team_project_quality": self.team_project_quality,
            "current_candidate_fit": self.current_candidate_fit,
            "opportunity_estimate": self.opportunity_estimate,
            "freshness_and_effort": self.freshness_and_effort,
        }

    def total(self) -> float:
        return sum(self.as_dict().values())


DEFAULT_WEIGHTS: dict[RankingMode, ModeWeights] = {
    # Platform dominates at internship stage.
    RankingMode.INTERNSHIP: ModeWeights(0.50, 0.20, 0.12, 0.10, 0.05, 0.03),
    # Actual work, team and comp start mattering more.
    RankingMode.NEW_GRAD: ModeWeights(0.32, 0.24, 0.18, 0.18, 0.05, 0.03),
    # Manager, responsibilities, comp, stability dominate.
    RankingMode.EXPERIENCED: ModeWeights(0.20, 0.24, 0.26, 0.22, 0.05, 0.03),
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
    version_label: str = "v2-internship-default"
    # Platform multipliers by company tier (non-linear platform advantage).
    platform_multiplier: dict[str, float] = field(
        default_factory=lambda: {"S": 1.18, "A": 1.10, "B": 1.04, "C": 1.00, "D": 0.85}
    )
    neutral_prior: float = 0.5

    @classmethod
    def for_mode(cls, mode: RankingMode) -> RankingProfile:
        return cls(
            mode=mode,
            weights=DEFAULT_WEIGHTS[mode],
            version_label=f"v2-{mode.value}-default",
        )
