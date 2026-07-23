"""The registry endpoints. Stateless by design — no sync has to have run."""

from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_registry_requires_auth(anon_client) -> None:
    r = await anon_client.get("/registry/companies")
    assert r.status_code in (401, 403, 503)


@pytest.mark.anyio
@pytest.mark.parametrize("view", ["apply", "value", "platform"])
async def test_each_view_returns_grouped_tiers(client, view: str) -> None:
    r = await client.get(f"/registry/companies?view={view}")
    assert r.status_code == 200
    body = r.json()
    assert body["view"] == view
    assert body["total"] > 150
    tiers = [g["tier"] for g in body["groups"]]
    assert tiers == [t for t in ("S", "A", "B", "C", "D") if t in tiers]
    assert sum(g["count"] for g in body["groups"]) == body["total"]


@pytest.mark.anyio
async def test_unknown_view_is_rejected(client) -> None:
    r = await client.get("/registry/companies?view=nonsense")
    assert r.status_code == 422


@pytest.mark.anyio
async def test_every_row_carries_both_axes(client) -> None:
    """A rank without value and access cannot be acted on: it does not say
    whether the constraint is reach or worth."""
    body = (await client.get("/registry/companies?view=value")).json()
    for group in body["groups"]:
        for c in group["companies"]:
            assert 0 <= c["value_score"] <= 100
            assert 0 <= c["access_score"] <= 100
            assert c["action"] in (
                "referral_or_outreach", "already_in_apply_queue", "watch")
            assert c["why"]


@pytest.mark.anyio
async def test_views_disagree(client) -> None:
    """If they agreed there would be no reason to serve both."""
    apply_ = (await client.get("/registry/companies?view=apply")).json()
    value = (await client.get("/registry/companies?view=value")).json()

    def top(body, n=20):
        out = []
        for g in body["groups"]:
            out.extend(c["key"] for c in g["companies"])
        return out[:n]

    assert len(set(top(apply_)) ^ set(top(value))) >= 6


@pytest.mark.anyio
async def test_posture_filter_finds_the_outreach_list(client) -> None:
    body = (await client.get(
        "/registry/companies?posture=worth_forcing")).json()
    keys = {c["key"] for g in body["groups"] for c in g["companies"]}
    assert {"openai", "anthropic"} <= keys
    assert 0 < body["total"] < 40


@pytest.mark.anyio
async def test_detail_shows_reproducible_arithmetic(client) -> None:
    """A score nobody can reproduce is an opinion wearing a number."""
    r = await client.get("/registry/company/openai")
    assert r.status_code == 200
    c = r.json()
    b = c["breakdown"]
    assert sum(b["value_terms"].values()) == pytest.approx(c["value_score"], abs=0.2)
    assert sum(b["access_terms"].values()) == pytest.approx(c["access_score"], abs=0.2)
    assert sum(b["platform_terms"].values()) == pytest.approx(
        c["platform_score"], abs=0.2)
    assert c["priority_score"] == pytest.approx(
        (c["value_score"] * c["access_score"]) ** 0.5, abs=0.2)


@pytest.mark.anyio
async def test_unknown_company_is_404(client) -> None:
    assert (await client.get("/registry/company/nope")).status_code == 404


@pytest.mark.anyio
async def test_meta_documents_the_method(client) -> None:
    m = (await client.get("/registry/meta")).json()
    assert m["total_rated"] > 150
    assert set(m["formulas"]) >= {"value", "access", "apply", "platform", "brand"}
    assert m["excluded_categories"] and m["gated_categories"]
    # Every judgment adjustment has to travel with its reason.
    for a in m["adjustments"]:
        assert a["reason"], a["name"]
    cov = m["source_coverage"]
    assert cov["with_known_board"] + cov["without_source"] == m["total_rated"]
