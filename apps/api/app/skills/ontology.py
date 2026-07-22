"""Skill ontology: canonical names, word-boundary matching, implication edges.

Replaces the old substring matching, which produced false positives such as
"postgresql" containing "sql" and therefore claiming SQL experience. Here,
PostgreSQL *implies* SQL through an explicit, explainable edge with its own
confidence — not through an accident of spelling.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

# --------------------------------------------------------------------------
# Canonicalization: many surface forms -> one canonical skill id.
# --------------------------------------------------------------------------
ALIASES: dict[str, str] = {
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "psql": "postgresql",
    "js": "javascript",
    "javascript": "javascript",
    "ts": "typescript",
    "typescript": "typescript",
    "restful apis": "rest_api",
    "restful api": "rest_api",
    "rest apis": "rest_api",
    "rest api": "rest_api",
    "torch": "pytorch",
    "pytorch": "pytorch",
    "tf": "tensorflow",
    "tensorflow": "tensorflow",
    "k8s": "kubernetes",
    "kubernetes": "kubernetes",
    "gcp": "google_cloud",
    "google cloud": "google_cloud",
    "aws": "aws",
    "amazon web services": "aws",
    "sql": "sql",
    "python": "python",
    "java": "java",
    "golang": "go",
    "go": "go",
    "c++": "cpp",
    "cpp": "cpp",
    "spark": "spark",
    "apache spark": "spark",
    "airflow": "airflow",
    "apache airflow": "airflow",
    "docker": "docker",
    "react": "react",
    "node": "nodejs",
    "node.js": "nodejs",
    "nodejs": "nodejs",
    "pandas": "pandas",
    "numpy": "numpy",
    "scikit-learn": "sklearn",
    "sklearn": "sklearn",
    "tableau": "tableau",
    "power bi": "power_bi",
    "powerbi": "power_bi",
    "excel": "excel",
    "r": "r_lang",
    "scala": "scala",
    "kafka": "kafka",
    "redis": "redis",
    "mongodb": "mongodb",
    "mysql": "mysql",
    "snowflake": "snowflake",
    "dbt": "dbt",
    "terraform": "terraform",
    "fastapi": "fastapi",
    "django": "django",
    "flask": "flask",
    "azure": "azure",
    "git": "git",
    "linux": "linux",
}

# --------------------------------------------------------------------------
# Implication edges: having X gives *partial* evidence of Y, with a stated
# strength. Explicit and explainable — never inferred from spelling.
# --------------------------------------------------------------------------
IMPLIES: dict[str, list[tuple[str, float]]] = {
    "postgresql": [("sql", 0.85)],
    "mysql": [("sql", 0.85)],
    "snowflake": [("sql", 0.8)],
    "dbt": [("sql", 0.75)],
    "spark": [("distributed_systems", 0.6)],
    "pytorch": [("machine_learning", 0.8), ("python", 0.7)],
    "tensorflow": [("machine_learning", 0.8), ("python", 0.7)],
    "sklearn": [("machine_learning", 0.7), ("python", 0.7)],
    "pandas": [("python", 0.8), ("data_analysis", 0.7)],
    "numpy": [("python", 0.8)],
    "fastapi": [("python", 0.85), ("rest_api", 0.8)],
    "django": [("python", 0.85), ("rest_api", 0.6)],
    "flask": [("python", 0.85), ("rest_api", 0.6)],
    "kubernetes": [("docker", 0.6), ("cloud", 0.6)],
    "aws": [("cloud", 0.9)],
    "azure": [("cloud", 0.9)],
    "google_cloud": [("cloud", 0.9)],
    "terraform": [("cloud", 0.7), ("infrastructure_as_code", 0.9)],
    "airflow": [("data_engineering", 0.7), ("python", 0.6)],
    "kafka": [("distributed_systems", 0.7)],
    "react": [("javascript", 0.85), ("frontend", 0.8)],
    "nodejs": [("javascript", 0.85)],
    "typescript": [("javascript", 0.8)],
    "power_bi": [("data_analysis", 0.7), ("bi", 0.9)],
    "tableau": [("data_analysis", 0.7), ("bi", 0.9)],
}


class EvidenceStrength(int, Enum):
    """How strongly the candidate can actually demonstrate a skill."""

    LISTED_ONLY = 1        # only appears in a Skills section
    COURSEWORK = 2         # used in a course
    PERSONAL_PROJECT = 3   # used in a personal project
    INTERNSHIP = 4         # used in an internship project
    PRODUCTION = 5         # sustained use in a production system
    CORE_OWNERSHIP = 6     # owned a core module

    @property
    def factor(self) -> float:
        return {1: 0.35, 2: 0.5, 3: 0.65, 4: 0.85, 5: 0.95, 6: 1.0}[self.value]


@dataclass
class CandidateSkillEvidence:
    skill: str
    strength: EvidenceStrength = EvidenceStrength.LISTED_ONLY
    last_used_year: int | None = None
    provable_on_resume: bool = False


@dataclass
class JDSkill:
    skill: str
    required: bool = True          # required vs preferred
    evidence: str = ""             # verbatim JD span


@dataclass
class SkillMatchDetail:
    skill: str
    required: bool
    matched: bool
    via: str = ""                  # "direct" | "implied:<source>" | ""
    strength_factor: float = 0.0
    contribution: float = 0.0


@dataclass
class FitBreakdown:
    known_evidence_score: float
    coverage: float
    conservative_score: float
    details: list[SkillMatchDetail] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    matched_required: list[str] = field(default_factory=list)


def canonical(term: str) -> str | None:
    """Map a surface form to a canonical skill id (None if unknown)."""
    return ALIASES.get(term.strip().lower())


def extract_skills(text: str | None) -> list[str]:
    """Word-boundary extraction of known skills. No substring matching.

    'PostgreSQL' will NOT produce 'sql' here — that relationship is expressed
    through IMPLIES, with an explicit confidence, not through spelling.
    """
    if not text:
        return []
    low = text.lower()
    found: list[str] = []
    for surface, canon in ALIASES.items():
        # Escape regex metacharacters (c++ etc.) and require token boundaries.
        pattern = r"(?<![a-z0-9+#.])" + re.escape(surface) + r"(?![a-z0-9+#])"
        if re.search(pattern, low):
            if canon not in found:
                found.append(canon)
    return found


def expand_with_implications(skills: dict[str, float]) -> dict[str, float]:
    """Add implied skills at reduced confidence. Direct evidence always wins."""
    out = dict(skills)
    for skill, conf in list(skills.items()):
        for implied, edge in IMPLIES.get(skill, []):
            candidate = conf * edge
            if candidate > out.get(implied, 0.0):
                out[implied] = candidate
    return out


def candidate_skill_map(evidence: list[CandidateSkillEvidence]) -> dict[str, float]:
    """Candidate skill -> effective strength in [0,1], including implications."""
    direct = {e.skill: e.strength.factor for e in evidence}
    return expand_with_implications(direct)


def compute_fit(
    jd_skills: list[JDSkill],
    candidate: list[CandidateSkillEvidence],
    *,
    neutral_prior: float = 0.5,
) -> FitBreakdown:
    """Evidence-weighted skill fit.

    Required skills weigh 1.0, preferred 0.4. Coverage reflects how much of the
    JD's requirement surface we could actually evaluate, so a thin JD cannot
    produce a confident-looking score. See docs/EVIDENCE_COVERAGE.md.
    """
    if not jd_skills:
        return FitBreakdown(0.0, 0.0, neutral_prior, [], [], [])

    cand = candidate_skill_map(candidate)
    details: list[SkillMatchDetail] = []
    num = 0.0
    den_conf = 0.0
    den_total = 0.0
    missing_required: list[str] = []
    matched_required: list[str] = []

    for jd in jd_skills:
        weight = 1.0 if jd.required else 0.4
        den_total += weight

        strength = cand.get(jd.skill, 0.0)
        via = ""
        if strength > 0:
            # Was it direct or implied?
            direct = any(e.skill == jd.skill for e in candidate)
            if direct:
                via = "direct"
            else:
                sources = [
                    s for s, edges in IMPLIES.items()
                    if any(t == jd.skill for t, _ in edges) and s in cand
                ]
                via = f"implied:{sources[0]}" if sources else "implied"

        # Confidence: we can always evaluate a skill we know the ontology for.
        confidence = 1.0 if jd.skill in ALIASES.values() else 0.4
        den_conf += weight * confidence
        num += weight * strength * confidence

        matched = strength > 0
        if jd.required:
            (matched_required if matched else missing_required).append(jd.skill)

        details.append(
            SkillMatchDetail(
                skill=jd.skill, required=jd.required, matched=matched, via=via,
                strength_factor=round(strength, 3),
                contribution=round(weight * strength * confidence, 3),
            )
        )

    known = num / den_conf if den_conf else 0.0
    coverage = den_conf / den_total if den_total else 0.0
    conservative = known * coverage + neutral_prior * (1 - coverage)

    return FitBreakdown(
        known_evidence_score=round(known, 4),
        coverage=round(coverage, 4),
        conservative_score=round(conservative, 4),
        details=details,
        missing_required=missing_required,
        matched_required=matched_required,
    )
