from __future__ import annotations

import pytest

from app.connectors.ashby import AshbyConnector
from app.connectors.greenhouse import GreenhouseConnector
from app.connectors.lever import LeverConnector
from app.schemas.connector import SourceConfig
from tests.fake_http import FakeHttp


@pytest.mark.asyncio
async def test_greenhouse_contract():
    http = FakeHttp({"greenhouse": "greenhouse/jobs.json"})
    conn = GreenhouseConnector()
    res = await conn.fetch(SourceConfig(connector_key="greenhouse", external_id="exampleco",
                                        display_name="ExampleCo"), http)
    assert len(res.raw_jobs) == 2
    job = res.raw_jobs[0]
    assert job.source_job_id == "1001"
    assert job.title == "Software Engineer, Backend"
    # canonical URL is the official ATS URL
    assert job.canonical_application_url == "https://boards.greenhouse.io/exampleco/jobs/1001"
    assert "sponsorship" in job.description_text.lower()
    assert job.content_hash


@pytest.mark.asyncio
async def test_lever_contract():
    http = FakeHttp({"lever": "lever/postings.json"})
    res = await LeverConnector().fetch(
        SourceConfig(connector_key="lever", external_id="exampleco", display_name="ExampleCo"),
        http,
    )
    assert len(res.raw_jobs) == 1
    job = res.raw_jobs[0]
    assert job.remote_mode == "hybrid"
    assert job.canonical_application_url.endswith("/apply")
    assert job.source_posted_at is not None


@pytest.mark.asyncio
async def test_ashby_contract():
    http = FakeHttp({"ashby": "ashby/jobs.json"})
    res = await AshbyConnector().fetch(
        SourceConfig(connector_key="ashby", external_id="exampleco", display_name="ExampleCo"),
        http,
    )
    job = res.raw_jobs[0]
    assert job.title == "Machine Learning Engineer"
    assert job.employment_type == "FullTime"
    assert "phd" in job.description_text.lower()


@pytest.mark.asyncio
async def test_not_modified_304():
    class NotModified:
        async def get_json(self, url, *, headers=None):
            return 304, {}, {}

    res = await GreenhouseConnector().fetch(
        SourceConfig(connector_key="greenhouse", external_id="x", display_name="x",
                     etag='W/"fixture"'),
        NotModified(),
    )
    assert res.not_modified is True
    assert res.raw_jobs == []
