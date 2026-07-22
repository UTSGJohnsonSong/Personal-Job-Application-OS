from __future__ import annotations

import re

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()

# Patterns used to redact PII before anything reaches logs or LLM request logs.
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)(\+?\d[\d\s().-]{7,}\d)(?!\d)")
_SSN_LIKE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except VerifyMismatchError:
        return False


def redact_pii(text: str) -> str:
    """Best-effort redaction. Applied to log/audit metadata and LLM payload logs.

    This is defense-in-depth, not the primary control: the primary control is
    never sending sensitive fields at all (see PII minimization).
    """
    if not text:
        return text
    text = _SSN_LIKE.sub("[REDACTED_ID]", text)
    text = _EMAIL.sub("[REDACTED_EMAIL]", text)
    text = _PHONE.sub("[REDACTED_PHONE]", text)
    return text
