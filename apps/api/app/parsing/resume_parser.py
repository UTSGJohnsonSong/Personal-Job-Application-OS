from __future__ import annotations

import re
from dataclasses import dataclass, field

# Minimal, deterministic resume parser. Everything it extracts is marked
# RESUME_EXTRACTED and starts user_confirmed=False — the user must confirm before
# any of it can be used in an application (see docs/PERSONAL_CONTEXT.md).


@dataclass
class ParsedResume:
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    education_lines: list[str] = field(default_factory=list)
    raw_sections: dict[str, str] = field(default_factory=dict)


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)(\+?\d[\d\s().-]{7,}\d)(?!\d)")
_SECTION = re.compile(
    r"^\s*(experience|education|skills|projects|summary|certifications)\s*:?\s*$", re.I
)


def parse_resume(text: str, *, known_skill_vocab: list[str] | None = None) -> ParsedResume:
    out = ParsedResume()
    out.emails = list(dict.fromkeys(_EMAIL.findall(text)))
    out.phones = list(dict.fromkeys(m.strip() for m in _PHONE.findall(text)))

    # Section splitting.
    current = "header"
    buf: list[str] = []
    for line in text.splitlines():
        m = _SECTION.match(line)
        if m:
            out.raw_sections[current] = "\n".join(buf).strip()
            current = m.group(1).lower()
            buf = []
        else:
            buf.append(line)
    out.raw_sections[current] = "\n".join(buf).strip()

    # Skills: ONLY match against a provided vocabulary — never invent skills.
    if known_skill_vocab:
        low = text.lower()
        out.skills = [s for s in known_skill_vocab if s.lower() in low]

    edu = out.raw_sections.get("education", "")
    out.education_lines = [ln.strip() for ln in edu.splitlines() if ln.strip()]
    return out
