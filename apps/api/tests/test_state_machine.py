from __future__ import annotations

import pytest

from app.applications.packet import build_packet_snapshot, packet_hash
from app.applications.state_machine import (
    AppStatus,
    IllegalTransition,
    SubmissionNotConfirmed,
    assert_transition,
    can_transition,
    guard_submit,
)


def test_cannot_jump_straight_to_submitted():
    assert not can_transition(AppStatus.PREPARING, AppStatus.SUBMITTED)
    with pytest.raises(IllegalTransition):
        assert_transition(AppStatus.PREPARING, AppStatus.SUBMITTED)


def test_submit_requires_confirmation():
    with pytest.raises(SubmissionNotConfirmed):
        guard_submit(
            AppStatus.WAITING_FOR_CONFIRMATION,
            confirmation_present=False,
            confirmed_by_user=False,
            confirmation_packet_hash=None,
            submitted_packet_hash="abc",
        )


def test_submit_requires_matching_packet_hash():
    # A confirmation for a different packet must NOT authorize this submission.
    with pytest.raises(SubmissionNotConfirmed):
        guard_submit(
            AppStatus.WAITING_FOR_CONFIRMATION,
            confirmation_present=True,
            confirmed_by_user=True,
            confirmation_packet_hash="hash_of_other_packet",
            submitted_packet_hash="hash_of_this_packet",
        )


def test_submit_succeeds_with_valid_confirmation():
    h = "matching_hash"
    guard_submit(
        AppStatus.WAITING_FOR_CONFIRMATION,
        confirmation_present=True,
        confirmed_by_user=True,
        confirmation_packet_hash=h,
        submitted_packet_hash=h,
    )  # no exception => allowed


def test_packet_hash_changes_when_answers_change():
    base = build_packet_snapshot(
        company="Acme", role="Engineer", official_url="https://x",
        resume_version_id="r1",
        answers=[{"question": "Q1", "answer": "A1"}],
        documents=["resume.pdf"], cover_letter=None,
    )
    changed = build_packet_snapshot(
        company="Acme", role="Engineer", official_url="https://x",
        resume_version_id="r1",
        answers=[{"question": "Q1", "answer": "A1-EDITED"}],
        documents=["resume.pdf"], cover_letter=None,
    )
    assert packet_hash(base) != packet_hash(changed)
