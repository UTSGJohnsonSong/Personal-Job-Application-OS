from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.applications.packet import build_packet_snapshot, packet_hash
from app.models.application import Application, ApplicationPacket
from app.models.sourcing import Job, JobSource
from app.models.user import User


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    r2 = await client.get("/health/db")
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_dashboard_overview(client):
    r = await client.get("/dashboard/overview")
    assert r.status_code == 200
    body = r.json()
    assert "totals" in body and "funnel" in body and "conversion" in body


async def _make_application(session, *, status="application_started"):
    user = User(email=f"t{datetime.now().timestamp()}@example.test", password_hash="x")
    session.add(user)
    await session.flush()
    src = JobSource(connector_key="greenhouse", external_id=f"e{datetime.now().timestamp()}",
                    display_name="Ex")
    session.add(src)
    await session.flush()
    job = Job(source_id=src.id, source_job_id="1", title="Engineer",
              normalized_title="engineer", first_seen_at=datetime.now(UTC))
    session.add(job)
    await session.flush()
    snapshot = build_packet_snapshot(
        company="Ex", role="Engineer", official_url="https://x",
        resume_version_id=None, answers=[{"question": "Q", "answer": "A"}],
        documents=["resume.pdf"], cover_letter=None,
    )
    ph = packet_hash(snapshot)
    packet = ApplicationPacket(job_id=job.id, user_id=user.id, status="ready", packet_hash=ph)
    session.add(packet)
    await session.flush()
    app_row = Application(user_id=user.id, job_id=job.id, packet_id=packet.id, status=status)
    session.add(app_row)
    await session.commit()
    return app_row.id, ph


@pytest.mark.asyncio
async def test_confirm_and_submit_happy_path(client, session):
    app_id, ph = await _make_application(session)
    r1 = await client.post(f"/applications/{app_id}/prepare-confirmation")
    assert r1.status_code == 200
    assert r1.json()["packet_hash"] == ph

    r2 = await client.post(f"/applications/{app_id}/confirm-and-submit",
                           json={"packet_hash_ack": ph})
    assert r2.status_code == 200
    assert r2.json()["status"] == "submitted"


@pytest.mark.asyncio
async def test_submit_rejected_with_wrong_hash(client, session):
    app_id, ph = await _make_application(session)
    await client.post(f"/applications/{app_id}/prepare-confirmation")
    r = await client.post(f"/applications/{app_id}/confirm-and-submit",
                          json={"packet_hash_ack": "WRONG_HASH"})
    assert r.status_code == 409  # confirmation does not match packet


@pytest.mark.asyncio
async def test_cannot_submit_without_prepared_confirmation(client, session):
    app_id, ph = await _make_application(session)
    # Skip prepare-confirmation entirely.
    r = await client.post(f"/applications/{app_id}/confirm-and-submit",
                          json={"packet_hash_ack": ph})
    assert r.status_code == 409
