from __future__ import annotations

import re
from dataclasses import dataclass, field

# Rule-based, deterministic JD parsing. An optional LLM enricher can add evidence
# text (see docs/DECISIONS.md D4), but numeric downstream paths never depend on it.
# All extracted requirements carry verbatim evidence spans.


@dataclass
class ExtractedRequirement:
    field: str
    value: str | None
    is_required: bool
    evidence: str
    confidence: float


@dataclass
class ParsedJD:
    employment_type: str | None = None
    degree_level: str | None = None
    needs_sponsorship_info: str | None = None  # e.g. "no sponsorship", "sponsorship available"
    years_experience: float | None = None
    languages: list[str] = field(default_factory=list)
    requires_cover_letter: bool = False
    requires_transcript: bool = False
    has_open_ended: bool = False
    requirements: list[ExtractedRequirement] = field(default_factory=list)


_DEGREE = [
    (re.compile(r"\bph\.?d\b", re.I), "phd"),
    (re.compile(r"\bmaster'?s?\b|\bm\.?s\.?c?\b", re.I), "masters"),
    (re.compile(r"\bbachelor'?s?\b|\bb\.?s\.?c?\b|\bb\.?a\b", re.I), "bachelors"),
    (re.compile(r"\bassociate'?s?\b", re.I), "associate"),
]
_EMPLOYMENT = [
    (re.compile(r"\bintern(ship)?\b", re.I), "internship"),
    (re.compile(r"\bco-?op\b", re.I), "coop"),
    (re.compile(r"\bnew ?grad(uate)?\b", re.I), "new_grad"),
    (re.compile(r"\bpart[- ]time\b", re.I), "part_time"),
    (re.compile(r"\bcontract(or)?\b", re.I), "contract"),
    (re.compile(r"\bfull[- ]time\b", re.I), "full_time"),
]
_NO_SPONSOR = re.compile(
    r"(not|unable to|cannot|do(es)? not)\s+(offer|provide|sponsor)[^.]{0,40}sponsor", re.I
)
_YES_SPONSOR = re.compile(r"sponsorship (is )?(available|offered|provided)", re.I)
_YEARS = re.compile(r"(\d{1,2})\+?\s*(?:years|yrs)", re.I)


def _find_span(text: str, pat: re.Pattern, width: int = 120) -> str:
    m = pat.search(text)
    if not m:
        return ""
    start = max(0, m.start() - width // 2)
    end = min(len(text), m.end() + width // 2)
    return text[start:end].strip()


def parse_jd(text: str | None, *, structured_hints: dict | None = None) -> ParsedJD:
    text = text or ""
    hints = structured_hints or {}
    out = ParsedJD()
    reqs: list[ExtractedRequirement] = []

    for pat, label in _EMPLOYMENT:
        if pat.search(text) or hints.get("employment_type", "").lower().find(label) >= 0:
            out.employment_type = label
            reqs.append(
                ExtractedRequirement(
                    "employment_type", label, True, _find_span(text, pat) or label, 0.7
                )
            )
            break

    for pat, label in _DEGREE:
        if pat.search(text):
            out.degree_level = label
            reqs.append(
                ExtractedRequirement("degree", label, True, _find_span(text, pat), 0.7)
            )
            break

    if _NO_SPONSOR.search(text):
        out.needs_sponsorship_info = "no_sponsorship"
        reqs.append(
            ExtractedRequirement(
                "sponsorship", "no_sponsorship", True, _find_span(text, _NO_SPONSOR), 0.8
            )
        )
    elif _YES_SPONSOR.search(text):
        out.needs_sponsorship_info = "sponsorship_available"
        reqs.append(
            ExtractedRequirement(
                "sponsorship", "sponsorship_available", False,
                _find_span(text, _YES_SPONSOR), 0.7
            )
        )

    ym = _YEARS.search(text)
    if ym:
        out.years_experience = float(ym.group(1))
        reqs.append(
            ExtractedRequirement(
                "years_experience", ym.group(1), True, _find_span(text, _YEARS), 0.6
            )
        )

    low = text.lower()
    out.requires_cover_letter = "cover letter" in low
    out.requires_transcript = "transcript" in low
    out.has_open_ended = bool(re.search(r"why do you|tell us about|in your own words", low))

    out.requirements = reqs
    return out
