from __future__ import annotations

from enum import StrEnum


class AppStatus(StrEnum):
    DISCOVERED = "discovered"
    SAVED = "saved"
    SKIPPED = "skipped"
    INELIGIBLE = "ineligible"
    PREPARING = "preparing"
    READY_FOR_REVIEW = "ready_for_review"
    APPLICATION_STARTED = "application_started"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    SUBMITTED = "submitted"
    CONFIRMATION_RECEIVED = "confirmation_received"
    RECRUITER_CONTACT = "recruiter_contact"
    ASSESSMENT = "assessment"
    PHONE_SCREEN = "phone_screen"
    INTERVIEW = "interview"
    FINAL_INTERVIEW = "final_interview"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    POSITION_CLOSED = "position_closed"
    OFFER = "offer"
    ACCEPTED = "accepted"


# Legal transitions. `submitted` is reachable ONLY from waiting_for_confirmation
# AND only when a valid per-job confirmation exists (enforced in submit()).
_TRANSITIONS: dict[AppStatus, set[AppStatus]] = {
    AppStatus.DISCOVERED: {AppStatus.SAVED, AppStatus.SKIPPED, AppStatus.INELIGIBLE,
                           AppStatus.PREPARING},
    AppStatus.SAVED: {AppStatus.PREPARING, AppStatus.SKIPPED, AppStatus.INELIGIBLE},
    AppStatus.PREPARING: {AppStatus.READY_FOR_REVIEW, AppStatus.SKIPPED},
    AppStatus.READY_FOR_REVIEW: {AppStatus.APPLICATION_STARTED, AppStatus.PREPARING,
                                 AppStatus.SKIPPED},
    AppStatus.APPLICATION_STARTED: {AppStatus.WAITING_FOR_CONFIRMATION, AppStatus.PREPARING,
                                    AppStatus.WITHDRAWN},
    AppStatus.WAITING_FOR_CONFIRMATION: {AppStatus.SUBMITTED, AppStatus.APPLICATION_STARTED,
                                         AppStatus.WITHDRAWN},
    AppStatus.SUBMITTED: {AppStatus.CONFIRMATION_RECEIVED, AppStatus.RECRUITER_CONTACT,
                          AppStatus.ASSESSMENT, AppStatus.REJECTED, AppStatus.WITHDRAWN,
                          AppStatus.POSITION_CLOSED},
    AppStatus.CONFIRMATION_RECEIVED: {AppStatus.RECRUITER_CONTACT, AppStatus.ASSESSMENT,
                                      AppStatus.REJECTED, AppStatus.POSITION_CLOSED},
    AppStatus.RECRUITER_CONTACT: {AppStatus.ASSESSMENT, AppStatus.PHONE_SCREEN,
                                  AppStatus.INTERVIEW, AppStatus.REJECTED, AppStatus.WITHDRAWN},
    AppStatus.ASSESSMENT: {AppStatus.PHONE_SCREEN, AppStatus.INTERVIEW, AppStatus.REJECTED,
                           AppStatus.WITHDRAWN},
    AppStatus.PHONE_SCREEN: {AppStatus.INTERVIEW, AppStatus.REJECTED, AppStatus.WITHDRAWN},
    AppStatus.INTERVIEW: {AppStatus.FINAL_INTERVIEW, AppStatus.OFFER, AppStatus.REJECTED,
                          AppStatus.WITHDRAWN},
    AppStatus.FINAL_INTERVIEW: {AppStatus.OFFER, AppStatus.REJECTED, AppStatus.WITHDRAWN},
    AppStatus.OFFER: {AppStatus.ACCEPTED, AppStatus.REJECTED, AppStatus.WITHDRAWN},
    # terminal-ish
    AppStatus.REJECTED: set(),
    AppStatus.WITHDRAWN: set(),
    AppStatus.POSITION_CLOSED: set(),
    AppStatus.ACCEPTED: set(),
    AppStatus.SKIPPED: {AppStatus.SAVED},
    AppStatus.INELIGIBLE: {AppStatus.SAVED},
}


class IllegalTransition(Exception):
    pass


class SubmissionNotConfirmed(Exception):
    """Raised when submission is attempted without a valid per-job confirmation."""


def can_transition(src: AppStatus, dst: AppStatus) -> bool:
    return dst in _TRANSITIONS.get(src, set())


def assert_transition(src: AppStatus, dst: AppStatus) -> None:
    if not can_transition(src, dst):
        raise IllegalTransition(f"{src.value} -> {dst.value} is not allowed")


def guard_submit(
    src: AppStatus,
    *,
    confirmation_present: bool,
    confirmed_by_user: bool,
    confirmation_packet_hash: str | None,
    submitted_packet_hash: str | None,
) -> None:
    """Hard invariant enforced before advancing to SUBMITTED.

    No confirmation, no submission — ever. Confirming one job never carries to
    another because the confirmation is bound to THIS packet's hash.
    """
    assert_transition(src, AppStatus.SUBMITTED)
    if not (confirmation_present and confirmed_by_user):
        raise SubmissionNotConfirmed("missing explicit per-job user confirmation")
    if not confirmation_packet_hash or confirmation_packet_hash != submitted_packet_hash:
        raise SubmissionNotConfirmed("confirmation does not match the packet being submitted")
