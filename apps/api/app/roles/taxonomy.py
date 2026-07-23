"""Standardized role taxonomy (R1–R4) and evidence-based classification.

Explicitly does NOT use naive title substring matching: `"engineer" in title`
misclassifies Sales/Solutions/Field/Support Engineer. Negative title signals are
evaluated FIRST, then word-boundary title phrases, then JD body signals which
can demote a title-based guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class RoleBand(StrEnum):
    R1 = "R1"  # core technical
    R2 = "R2"  # high-value adjacent
    R3 = "R3"  # context-dependent
    R4 = "R4"  # low transferability

    @property
    def base_transferability(self) -> float:
        return {"R1": 1.0, "R2": 0.9, "R3": 0.8, "R4": 0.1}[self.value]


ROLE_TYPES: dict[str, RoleBand] = {
    # R1
    "software_engineering": RoleBand.R1,
    "backend_engineering": RoleBand.R1,
    "data_engineering": RoleBand.R1,
    "machine_learning_engineering": RoleBand.R1,
    "applied_ai": RoleBand.R1,
    "ml_infrastructure": RoleBand.R1,
    "platform_engineering": RoleBand.R1,
    "cloud_engineering": RoleBand.R1,
    # R2
    "analytics_engineering": RoleBand.R2,
    "technical_product": RoleBand.R2,
    "ai_product": RoleBand.R2,
    "product_engineering": RoleBand.R2,
    "technical_program_management": RoleBand.R2,
    "data_platform_analyst": RoleBand.R2,
    "high_technical_product_analyst": RoleBand.R2,
    # R3
    "data_analyst": RoleBand.R3,
    "bi_analyst": RoleBand.R3,
    "business_systems_analyst": RoleBand.R3,
    "technology_analyst": RoleBand.R3,
    "solutions_engineer": RoleBand.R3,
    "technical_project_management": RoleBand.R3,
    "general_product_analyst": RoleBand.R3,
    # R4
    "sales": RoleBand.R4,
    "customer_support": RoleBand.R4,
    "hr": RoleBand.R4,
    "general_marketing": RoleBand.R4,
    "nontechnical_operations": RoleBand.R4,
    "administrative": RoleBand.R4,
    "nontechnical_business_development": RoleBand.R4,
}

# Negative title signals evaluated BEFORE anything else. These win over the
# presence of the word "engineer"/"technical".
_NEGATIVE_TITLE: list[tuple[str, str]] = [
    (r"\bsales\s+engineer\b", "solutions_engineer"),
    (r"\bsolutions?\s+engineer\b", "solutions_engineer"),
    (r"\bsales\s+development\b", "sales"),
    (r"\bfield\s+engineer\b", "customer_support"),
    (r"\bsupport\s+engineer\b", "customer_support"),
    (r"\bcustomer\s+success\b", "customer_support"),
    (r"\baccount\s+(executive|manager)\b", "sales"),
    (r"\bbusiness\s+development\b", "nontechnical_business_development"),
    (r"\brecruit(er|ing|ment)\b", "hr"),
    (r"\bhuman\s+resources\b|\bHRBP\b|\bHR\s+(business\s+partner|generalist)\b", "hr"),
    (r"\bressources\s+humaines\b", "hr"),
    (r"\btalent\s+(acquisition|partner|management)\b", "hr"),
    (r"\bpeople\s+(operations|partner|team|&\s+culture)\b", "hr"),
    (r"\bcompensation|\bbenefits\s+(analyst|specialist|manager)\b", "hr"),
    (r"\bmarketing\b", "general_marketing"),
    (r"\bcontent\s+(writer|creator|strategist|marketing)\b", "general_marketing"),
    (r"\b(copy)?writer\b", "general_marketing"),
    (r"\bcommunications?\s+(specialist|manager|coordinator)\b", "general_marketing"),
    (r"\bsocial\s+media\b", "general_marketing"),
    (r"\bbrand\b", "general_marketing"),
    (r"\bevents?\s+(specialist|coordinator|manager)\b", "nontechnical_operations"),
    (r"\btradeshows?\b", "nontechnical_operations"),
    (r"\badministrative\b|\badmin\s+assistant\b", "administrative"),
    (r"\bexecutive\s+assistant\b", "administrative"),
    (r"\boffice\s+(manager|coordinator|administrator)\b", "administrative"),
    (r"\bclient\s+success\b", "customer_support"),
    (r"\b(client|customer)\s+experience\b", "customer_support"),
    (r"\brelationship\s+manager\b", "sales"),
    (r"\brecouvrement\b|\bcollections?\s+(agent|specialist)\b", "nontechnical_operations"),
    (r"\bagent(e)?\b", "customer_support"),
    (r"\blegal\s+counsel\b|\bparalegal\b", "administrative"),
    (r"\baccountant\b|\bbookkeep|\baccounting\s+(operations|clerk|analyst)\b",
     "administrative"),
    (r"\bcomptable|\bcomptabilit", "administrative"),  # French: accounting
    (r"\bapprovisionnement\b|\bprocurement\b", "nontechnical_operations"),
    (r"\bvente(s)?\b", "sales"),  # French: sales
    (r"\bfacilities\b|\breceptionist\b", "administrative"),
    # Generic sales/support titles, checked after the more specific ones above.
    (r"\bsales\b", "sales"),
    (r"\bcustomer\s+(support|service)\b", "customer_support"),
]

# Positive title phrases (word-boundary, ordered most-specific first).
_TITLE_PHRASES: list[tuple[str, str]] = [
    (r"\bmachine\s+learning\s+(engineer|intern)\b", "machine_learning_engineering"),
    (r"\bml\s+(engineer|infrastructure)\b", "machine_learning_engineering"),
    (r"\bapplied\s+(ai|scientist|ml)\b", "applied_ai"),
    (r"\b(ai|ml)\s+product\b", "ai_product"),
    (r"\bdata\s+engineer\b", "data_engineering"),
    (r"\banalytics\s+engineer\b", "analytics_engineering"),
    (r"\bplatform\s+engineer\b", "platform_engineering"),
    (r"\b(cloud|infrastructure|devops|site\s+reliability)\s+engineer\b", "cloud_engineering"),
    (r"\bbackend\b|\bback[-\s]end\b", "backend_engineering"),
    (r"\btechnical\s+program\s+manager\b", "technical_program_management"),
    (r"\btechnical\s+product\s+manager\b", "technical_product"),
    (r"\bproduct\s+manager\b", "technical_product"),
    (r"\bbusiness\s+intelligence\b|\bbi\s+analyst\b", "bi_analyst"),
    (r"\bbusiness\s+systems\s+analyst\b", "business_systems_analyst"),
    (r"\bdata\s+analyst\b", "data_analyst"),
    (r"\btechnology\s+analyst\b", "technology_analyst"),
    (r"\bproject\s+manager\b", "technical_project_management"),
    (r"\bsoftware\s+(development\s+)?engineer\b", "software_engineering"),
    (r"\bsoftware\s+developer\b", "software_engineering"),
    (r"\bdeveloper\b", "software_engineering"),
    (r"\bengineer\b", "software_engineering"),  # last resort, only after negatives
]

# Body signals confirming genuine technical content.
_TECH_BODY = [
    r"\bcode\b", r"\bcoding\b", r"\bapi\b", r"\bdatabase", r"\bpipeline",
    r"\bsystem design\b", r"\bdeploy", r"\bproduction\b", r"\btesting\b",
    r"\bmonitor", r"\bmodel\b", r"\balgorithm", r"\bcloud\b", r"\bsql\b",
    r"\bpython\b", r"\bjava\b", r"\bdistributed\b", r"\bmicroservice",
]
_NONTECH_BODY = [
    r"\bquota\b", r"\bcold call", r"\bpipeline of (leads|prospects)\b",
    r"\bclient relationship", r"\bupsell", r"\bcommission\b",
]


@dataclass
class RoleClassification:
    """Three explicit layers, never collapsed into one opaque label.

    Title rules give stability; JD body gives understanding. A "Data Analyst"
    doing experimentation and data modelling can be promoted; a "Solutions
    Engineer" doing pure sales stays demoted. Both directions keep evidence.
    """

    role_type: str
    band: RoleBand                      # final category
    confidence: float
    # --- the three layers ---
    title_prior_type: str = ""
    title_prior_band: RoleBand | None = None
    jd_content_band: RoleBand | None = None
    jd_content_summary: str = ""
    adjustment: str = "none"            # promoted | demoted | none
    evidence: list[str] = field(default_factory=list)
    signals_positive: list[str] = field(default_factory=list)
    signals_negative: list[str] = field(default_factory=list)
    needs_review: bool = False
    technical_density: float = 0.0      # 0..1, drives R3/R4 transferability

    @property
    def transferability(self) -> float:
        """R3 varies 0.7–0.9 by evidenced technical content; R4 0.0–0.2."""
        if self.band is RoleBand.R3:
            return round(0.7 + 0.2 * self.technical_density, 3)
        if self.band is RoleBand.R4:
            return round(0.2 * self.technical_density, 3)
        return self.band.base_transferability


def _span(text: str, pattern: str, width: int = 90) -> str:
    m = re.search(pattern, text, re.I)
    if not m:
        return ""
    s = max(0, m.start() - width // 2)
    e = min(len(text), m.end() + width // 2)
    return text[s:e].strip()


def classify_role(title: str | None, description: str | None = None) -> RoleClassification:
    """Classify a posting. Title alone caps confidence and flags needs_review."""
    title_l = (title or "").lower()
    body = description or ""
    body_l = body.lower()

    positives: list[str] = []
    negatives: list[str] = []
    evidence: list[str] = []

    # 1) Negative title signals FIRST — these override the word "engineer".
    role_type: str | None = None
    for pattern, mapped in _NEGATIVE_TITLE:
        if re.search(pattern, title_l):
            role_type = mapped
            negatives.append(f"title matches non-core pattern: {pattern}")
            evidence.append(_span(title_l, pattern) or title_l)
            break

    # 2) Positive title phrases.
    if role_type is None:
        for pattern, mapped in _TITLE_PHRASES:
            if re.search(pattern, title_l):
                role_type = mapped
                positives.append(f"title matches {mapped}")
                evidence.append(_span(title_l, pattern) or title_l)
                break

    if role_type is None:
        return RoleClassification(
            role_type="unknown", band=RoleBand.R3, confidence=0.2,
            evidence=[title or ""], needs_review=True, technical_density=0.0,
        )

    band = ROLE_TYPES[role_type]

    # 3) Body signals — measure real technical density.
    tech_hits = [p for p in _TECH_BODY if re.search(p, body_l)]
    nontech_hits = [p for p in _NONTECH_BODY if re.search(p, body_l)]
    density = 0.0
    if body_l:
        density = min(1.0, len(tech_hits) / 6.0)
        if nontech_hits:
            density = max(0.0, density - 0.15 * len(nontech_hits))
    for p in tech_hits[:4]:
        positives.append(f"body: {p}")
        sp = _span(body, p)
        if sp:
            evidence.append(sp)
    for p in nontech_hits[:3]:
        negatives.append(f"body: {p}")

    # 4) Independent JD-content classification. Depth signals that indicate the
    #    work is genuinely technical regardless of what the title says.
    depth_signals = [
        r"\bexperiment", r"\bdata model", r"\bmodel(l)?ing\b", r"\betl\b",
        r"\bstatistic", r"\bab test", r"\ba/b test", r"\bwarehouse\b",
        r"\bschema\b", r"\bquery optimi", r"\bmachine learning\b",
    ]
    depth_hits = [p for p in depth_signals if re.search(p, body_l)]
    if not body_l:
        jd_band = None
        jd_summary = "no job description available"
    elif density >= 0.5 and depth_hits:
        jd_band = RoleBand.R2
        jd_summary = f"substantial technical content ({len(tech_hits)} signals, depth work)"
    elif density >= 0.5:
        jd_band = RoleBand.R1
        jd_summary = f"heavy technical content ({len(tech_hits)} signals)"
    elif density >= 0.25:
        jd_band = RoleBand.R3
        jd_summary = f"moderate technical content ({len(tech_hits)} signals)"
    else:
        jd_band = RoleBand.R4 if nontech_hits else RoleBand.R3
        jd_summary = "little or no technical content"

    title_prior_type, title_prior_band = role_type, band
    adjustment = "none"

    # 5) Reconcile. Content may move the category by at most one band, in either
    #    direction, and the reason is always recorded.
    order = [RoleBand.R1, RoleBand.R2, RoleBand.R3, RoleBand.R4]
    if jd_band is not None:
        ti, ji = order.index(band), order.index(jd_band)
        if ji < ti:  # content is stronger than the title implied -> promote one
            band = order[ti - 1]
            adjustment = "promoted"
            positives.append(
                f"JD content stronger than title prior ({title_prior_band.value}"
                f" -> {band.value}): {jd_summary}"
            )
        elif ji > ti and (nontech_hits or density < 0.15):
            band = order[min(len(order) - 1, ti + 1)]
            adjustment = "demoted"
            negatives.append(
                f"JD content weaker than title prior ({title_prior_band.value}"
                f" -> {band.value}): {jd_summary}"
            )
            if band in (RoleBand.R3, RoleBand.R4) and title_prior_band is RoleBand.R1:
                role_type = "solutions_engineer"

    confidence = 0.55 if not body_l else min(0.95, 0.6 + 0.35 * density)
    if adjustment != "none":
        confidence = min(0.9, confidence + 0.05)  # corroborated by two layers
    needs_review = not body_l or confidence < 0.5

    return RoleClassification(
        role_type=role_type, band=band, confidence=round(confidence, 3),
        title_prior_type=title_prior_type, title_prior_band=title_prior_band,
        jd_content_band=jd_band, jd_content_summary=jd_summary,
        adjustment=adjustment,
        evidence=[e for e in evidence if e][:5],
        signals_positive=positives, signals_negative=negatives,
        needs_review=needs_review, technical_density=round(density, 3),
    )
