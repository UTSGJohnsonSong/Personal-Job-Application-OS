"""End-to-end tests for the apply-queue → record → status workflow."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.sourcing import Job, JobSource
from app.models.user import User


async def _make_job(session, title="Backend Engineer") -> str:
    stamp = datetime.now().timestamp()
    existing = (await session.execute(select(User).limit(1))).scalars().first()
    if existing is None:
        session.add(User(email=f"u{stamp}@example.test", password_hash="x"))
    src = JobSource(connector_key="greenhouse", external_id=f"b{stamp}", display_name="Ex")
    session.add(src)
    await session.flush()
    job = Job(
        source_id=src.id, source_job_id=f"j{stamp}", title=title,
        normalized_title=title.lower(), first_seen_at=datetime.now(UTC),
        canonical_application_url=f"https://example.test/apply/{stamp}",
        source_status="open", freshness_score=0.9,
    )
    session.add(job)
    await session.commit()
    return job.id


async def _uid(session) -> str:
    return (await session.execute(select(User.id).limit(1))).scalar_one()


# ------------------------------------------------------------------ auth

@pytest.mark.asyncio
async def test_protected_routes_reject_anonymous(anon_client):
    for path in ("/jobs", "/dashboard/overview", "/queue", "/records", "/ammo"):
        r = await anon_client.get(path)
        assert r.status_code == 401, f"{path} must require a token, got {r.status_code}"


@pytest.mark.asyncio
async def test_wrong_token_rejected(anon_client):
    r = await anon_client.get("/queue", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_health_stays_public(anon_client):
    assert (await anon_client.get("/health")).status_code == 200


# ------------------------------------------------------------------ queue

@pytest.mark.asyncio
async def test_queue_add_list_remove(client, session):
    job_id = await _make_job(session)

    r = await client.post(f"/queue/{job_id}", json={"note": "priority target"})
    assert r.status_code == 200
    app_id = r.json()["application_id"]

    q = (await client.get("/queue")).json()
    assert any(i["job_id"] == job_id for i in q["items"])
    entry = next(i for i in q["items"] if i["job_id"] == job_id)
    assert entry["queue_note"] == "priority target"
    assert entry["apply_url"]

    # Idempotent: adding twice does not duplicate.
    await client.post(f"/queue/{job_id}", json={})
    q2 = (await client.get("/queue")).json()
    assert sum(1 for i in q2["items"] if i["job_id"] == job_id) == 1

    assert (await client.delete(f"/queue/{job_id}")).status_code == 200
    q3 = (await client.get("/queue")).json()
    assert not any(i["job_id"] == job_id for i in q3["items"])
    assert app_id


@pytest.mark.asyncio
async def test_queue_orders_by_priority_then_score(client, session):
    a = await _make_job(session, "Alpha Role")
    b = await _make_job(session, "Beta Role")
    await client.post(f"/queue/{a}", json={})
    await client.post(f"/queue/{b}", json={})
    # Manual priority wins over score.
    await client.patch(f"/queue/{b}/priority", json={"priority": 1})
    items = (await client.get("/queue")).json()["items"]
    ids = [i["job_id"] for i in items]
    assert ids.index(b) < ids.index(a)


# ------------------------------------------------------------------ records

@pytest.mark.asyncio
async def test_record_answers_and_expand(client, session):
    job_id = await _make_job(session)
    app_id = (await client.post(f"/queue/{job_id}", json={})).json()["application_id"]

    payload = {
        "answers": [
            {"question": "Full name", "answer": "Test Candidate",
             "answer_source": "personal_context.name"},
            {"question": "Why this company?", "answer": "draft text",
             "source": "generated_draft"},
            {"question": "Do you require sponsorship?", "answer": None,
             "is_sensitive": True, "needs_user_input": True},
        ],
        "cover_letter": "Dear team...",
        "documents": ["resume_v1.pdf"],
        "uncertainties": ["sponsorship answer left to user"],
    }
    r = await client.put(f"/records/{app_id}", json=payload)
    assert r.status_code == 200
    assert r.json()["answers_recorded"] == 3
    first_hash = r.json()["packet_hash"]

    rec = (await client.get(f"/records/{app_id}")).json()
    assert len(rec["answers"]) == 3
    sensitive = next(a for a in rec["answers"] if a["is_sensitive"])
    assert sensitive["needs_user_input"] is True
    assert sensitive["answer"] is None  # never auto-answered
    drafted = next(a for a in rec["answers"] if a["provenance"] == "generated_draft")
    assert drafted["user_confirmed"] is False
    assert rec["cover_letter"] == "Dear team..."

    # Editing an answer changes the packet hash (invalidates prior confirmation).
    payload["answers"][1]["answer"] = "edited text"
    r2 = await client.put(f"/records/{app_id}", json=payload)
    assert r2.json()["packet_hash"] != first_hash
    assert r2.json()["answers_recorded"] == 3  # replaced, not duplicated


@pytest.mark.asyncio
async def test_status_switch_and_submitted_is_blocked(client, session):
    job_id = await _make_job(session)
    app_id = (await client.post(f"/queue/{job_id}", json={})).json()["application_id"]

    r = await client.post(f"/records/{app_id}/status", json={"status": "interview"})
    assert r.status_code == 200 and r.json()["to"] == "interview"

    rec = (await client.get(f"/records/{app_id}")).json()
    assert rec["status"] == "interview"
    assert any(e["event"] == "manual_status_change" for e in rec["timeline"])

    # The manual switch must never be a backdoor to `submitted`.
    blocked = await client.post(f"/records/{app_id}/status", json={"status": "submitted"})
    assert blocked.status_code == 409


# ------------------------------------------------------------------ ammo

@pytest.mark.asyncio
async def test_ammo_master_and_variants(client, session):
    await _make_job(session)  # ensures a user exists

    master = (await client.post("/ammo", json={
        "category": "resume_bullet",
        "title": "Pipeline bullet 母本",
        "content": "Built an ETL pipeline processing X records daily.",
        "tags": ["etl", "python"], "contains_metrics": True,
    })).json()
    assert master["is_master"] is True

    variant = (await client.post("/ammo", json={
        "category": "resume_bullet",
        "title": "Pipeline bullet — 银行方向",
        "content": "Built a regulatory data pipeline...",
        "direction": "banking", "variant_of": master["id"],
    })).json()
    assert variant["is_master"] is False

    lib = (await client.get("/ammo?category=resume_bullet")).json()
    group = next(g for g in lib["groups"] if g["id"] == master["id"])
    assert any(v["id"] == variant["id"] for v in group["variants"])

    used = (await client.post(f"/ammo/{master['id']}/used")).json()
    assert used["usage_count"] == 1

    found = (await client.get("/ammo?q=regulatory")).json()
    assert found["count"] >= 1

    assert (await client.delete(f"/ammo/{variant['id']}")).status_code == 200
    after = (await client.get("/ammo?category=resume_bullet")).json()
    assert all(
        variant["id"] != v["id"]
        for g in after["groups"] for v in g["variants"]
    )


# ------------------------------------------------------------------ manual entry

@pytest.mark.asyncio
async def test_manual_job_entry_records_unverified_state(client, session):
    await _make_job(session)  # ensure a user exists
    r = await client.post("/manual/jobs", json={
        "company_name": "Example Bank",
        "title": "Data Engineering Analyst (8-month co-op)",
        "apply_url": "https://jobs.example-bank.test/123",
        "initial_status": "application_started",
        "note": "applied via official site; submission unconfirmed",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "application_started"
    assert body["warnings"]  # must warn that nothing was verified

    rec = (await client.get(f"/records/{body['application_id']}")).json()
    assert rec["job"]["source_status"] == "unknown"   # never claimed to be open


@pytest.mark.asyncio
async def test_manual_entry_cannot_declare_submitted(client, session):
    await _make_job(session)
    r = await client.post("/manual/jobs", json={
        "company_name": "Example Bank",
        "title": "Analyst",
        "initial_status": "submitted",
    })
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_purge_requires_exact_confirmation(client, session):
    await _make_job(session)
    assert (await client.post("/manual/purge-demo-data",
                              json={"confirm": "yes"})).status_code == 400


@pytest.mark.asyncio
async def test_purge_clears_jobs_and_fictional_personal_context(client, session):
    from app.models.personal import CandidateSkill
    await _make_job(session)
    session.add(CandidateSkill(user_id=(await _uid(session)), name="python",
                               user_confirmed=True))
    await session.commit()

    r = await client.post("/manual/purge-demo-data",
                          json={"confirm": "PURGE DEMO DATA"})
    assert r.status_code == 200
    purged = r.json()["purged"]
    assert purged["jobs"] >= 1
    assert purged["candidate_skills"] >= 1          # fake facts about the user go too
    assert (await client.get("/jobs")).json()["count"] == 0
