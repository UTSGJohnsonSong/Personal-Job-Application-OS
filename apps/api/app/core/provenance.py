from __future__ import annotations

from enum import Enum, StrEnum


class ProvenanceSource(StrEnum):
    """Where a claim about the user or the world originated.

    Only USER_CONFIRMED (and user-confirmed RESUME_EXTRACTED) may ever be used in
    a real application. See docs/PERSONAL_CONTEXT.md.
    """

    USER_CONFIRMED = "user_confirmed"
    RESUME_EXTRACTED = "resume_extracted"
    IMPORTED_DOCUMENT = "imported_document"
    INFERRED_BUT_UNCONFIRMED = "inferred_but_unconfirmed"
    GENERATED_DRAFT = "generated_draft"
    CONNECTOR = "connector"
    EMAIL_INGEST = "email_ingest"
    SYSTEM = "system"


class SensitivityLevel(StrEnum):
    LOW = "low"
    PII = "pii"
    SENSITIVE_LEGAL = "sensitive_legal"  # work auth, GPA, demographics


class SourcePriority(int, Enum):
    FIRST_PARTY_ATS = 1
    GOV_UNIVERSITY_INSTITUTIONAL = 2
    AGGREGATOR = 3


def can_use_for_application(source: ProvenanceSource, user_confirmed: bool) -> bool:
    """A fact may feed a real application only when the user has confirmed it."""
    return user_confirmed and source in {
        ProvenanceSource.USER_CONFIRMED,
        ProvenanceSource.RESUME_EXTRACTED,
        ProvenanceSource.IMPORTED_DOCUMENT,
    }
