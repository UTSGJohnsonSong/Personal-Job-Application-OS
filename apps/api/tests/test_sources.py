"""Tests for the source catalog, the new connectors and canonicalization."""

from __future__ import annotations

import pytest

from app.connectors.jsonld import (
    JsonLdCareerConnector,
    extract_jsonld_blocks,
    job_from_jsonld,
)
from app.connectors.registry import all_connectors, get_connector
from app.connectors.user_import import UserImportConnector, parse_rows
from app.ingestion.canonicalize import (
    ResolutionStatus,
    apply_resolution,
    identify_ats,
    is_aggregator,
    resolve,
    titles_match,
)
from app.schemas.connector import SourceConfig
from app.sources.catalog import (
    BY_KEY,
    CATALOG,
    AccessMode,
    CanonicalPolicy,
    Maturity,
    requires_canonical_resolution,
)

# ------------------------------------------------------------------- catalog

def test_catalog_covers_the_requested_25_sources():
    assert len(CATALOG) == 25
    for key in ("greenhouse", "lever", "ashby", "smartrecruiters", "workday",
                "successfactors", "icims", "taleo_orc", "jsonld_career_page",
                "sitemap_career_page", "job_bank", "gc_jobs",
                "ontario_public_service", "city_of_toronto", "ttc", "metrolinx",
                "uoft_clnx", "linkedin", "indeed_email", "techto", "communitech",
                "mars", "vector_talent", "dmz", "wellfound"):
        assert key in BY_KEY, f"{key} missing from the catalog"


def test_account_bound_sources_are_never_scraped():
    """CLNx / LinkedIn / Indeed require the user's own login: import only."""
    for key in ("uoft_clnx", "linkedin", "indeed_email"):
        assert BY_KEY[key].access is AccessMode.USER_IMPORT
        assert BY_KEY[key].connector_key == "user_import"


def test_blocked_source_is_not_scraped():
    """A site that refuses automated access must not be given a scraping path."""
    wf = BY_KEY["wellfound"]
    assert wf.maturity is Maturity.BLOCKED
    assert wf.access is AccessMode.USER_IMPORT
    assert "403" in wf.notes


def test_aggregators_must_resolve_to_the_employer():
    # MaRS moved to first-party: its official careers page resolves to its own
    # BambooHR board, so it is no longer discovery-only.
    for key in ("linkedin", "indeed_email", "wellfound", "job_bank", "techto",
                "communitech", "vector_talent", "dmz"):
        assert BY_KEY[key].canonical_policy is CanonicalPolicy.RESOLVE_TO_EMPLOYER
        assert requires_canonical_resolution(key)


def test_first_party_ats_are_already_canonical():
    for key in ("greenhouse", "lever", "ashby", "smartrecruiters", "workday",
                "taleo_orc", "mars"):
        assert BY_KEY[key].canonical_policy is CanonicalPolicy.ALREADY_CANONICAL
        assert BY_KEY[key].priority <= 2


def test_every_catalog_connector_is_registered():
    registered = set(all_connectors())
    for spec in CATALOG:
        if spec.connector_key and spec.maturity in (
                Maturity.LIVE, Maturity.IMPLEMENTED_UNVERIFIED, Maturity.USER_IMPORT):
            assert spec.connector_key in registered, spec.key


# ------------------------------------------------------------------- JSON-LD

SAMPLE_HTML = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting",
 "title":"Data Engineering Analyst, Co-op",
 "datePosted":"2026-07-20",
 "hiringOrganization":{"@type":"Organization","name":"Acme Bank"},
 "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress",
   "addressLocality":"Toronto","addressRegion":"ON","addressCountry":"CA"}},
 "employmentType":"INTERN",
 "url":"https://acme.example/careers/123",
 "description":"<p>Build <b>ETL</b> pipelines.</p>"}
</script>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Organization","name":"Acme Bank"}
</script>
</head><body></body></html>
"""


def test_jsonld_extracts_only_job_postings():
    blocks = extract_jsonld_blocks(SAMPLE_HTML)
    assert len(blocks) == 2  # both blocks parse
    job = job_from_jsonld(blocks[0], page_url="https://acme.example/careers/123")
    assert job is not None
    assert job.title == "Data Engineering Analyst, Co-op"
    assert job.company_name == "Acme Bank"
    assert job.locations[0].raw_text == "Toronto, ON, CA"
    assert "ETL" in (job.description_text or "")   # HTML stripped, text kept
    assert job.canonical_application_url == "https://acme.example/careers/123"


def test_jsonld_handles_graph_and_remote():
    html = """<script type="application/ld+json">
    {"@graph":[{"@type":"JobPosting","title":"Remote Analyst",
      "jobLocationType":"TELECOMMUTE","url":"https://x.example/j/1"}]}
    </script>"""
    blocks = extract_jsonld_blocks(html)
    from app.connectors.jsonld import _is_job_posting, _walk

    nodes = [n for b in blocks for n in _walk(b) if _is_job_posting(n)]
    assert len(nodes) == 1
    job = job_from_jsonld(nodes[0], page_url=None)
    assert job.remote_mode == "remote"
    assert job.locations[0].raw_text == "Remote"


def test_jsonld_survives_malformed_block():
    html = '<script type="application/ld+json">{not json at all}</script>' + SAMPLE_HTML
    assert len(extract_jsonld_blocks(html)) == 2  # bad block skipped, good ones kept


@pytest.mark.asyncio
async def test_jsonld_connector_reads_pages():
    class FakeHttp:
        async def get_text(self, url, *, headers=None):
            return 200, SAMPLE_HTML, {}

    res = await JsonLdCareerConnector().fetch(
        SourceConfig(connector_key="jsonld", external_id="acme", display_name="Acme",
                     config={"urls": ["https://acme.example/careers"]}),
        FakeHttp(),
    )
    assert len(res.raw_jobs) == 1
    assert res.diagnostics["postings"] == 1


# --------------------------------------------------------------- user import

def test_user_import_parses_free_text():
    rows = parse_rows(
        "Data Analyst Intern at Acme Bank  https://linkedin.com/jobs/1\n"
        "Backend Developer Co-op - Beta Corp\n"
        "\n"
    )
    assert len(rows) == 2
    assert rows[0]["title"] == "Data Analyst Intern"
    assert rows[0]["company"] == "Acme Bank"
    assert rows[0]["url"].startswith("https://linkedin.com")
    assert rows[1]["company"] == "Beta Corp"


def test_user_import_parses_csv():
    rows = parse_rows(
        "Title,Company,Location,URL\n"
        "Data Analyst Co-op,Acme Bank,Toronto,https://acme.example/j/1\n"
    )
    assert rows == [{"title": "Data Analyst Co-op", "company": "Acme Bank",
                     "location": "Toronto", "url": "https://acme.example/j/1",
                     "deadline": None}]


@pytest.mark.asyncio
async def test_user_import_never_sets_canonical_url():
    """A user-pasted link is DISCOVERY. It must not become the official link."""
    res = await UserImportConnector().fetch(
        SourceConfig(connector_key="user_import", external_id="clnx",
                     display_name="CLNx",
                     config={"origin": "uoft_clnx",
                             "text": "Data Analyst Intern at Acme  https://clnx.example/1"}),
        object(),
    )
    job = res.raw_jobs[0]
    assert job.canonical_application_url is None
    assert job.official_source_url is None
    assert job.source_status == "unknown"
    assert job.raw["discovery_url"] == "https://clnx.example/1"


# ------------------------------------------------------------ canonicalization

def test_identifies_employer_ats_hosts():
    assert identify_ats("https://boards.greenhouse.io/acme/jobs/1") == "greenhouse"
    assert identify_ats("https://jobs.lever.co/acme/x") == "lever"
    assert identify_ats("https://jobs.ashbyhq.com/acme/x") == "ashby"
    assert identify_ats("https://acme.wd3.myworkdayjobs.com/en-US/x") == "workday"
    assert identify_ats("https://www.linkedin.com/jobs/view/1") is None


def test_identifies_aggregators():
    assert is_aggregator("https://www.linkedin.com/jobs/view/1")
    assert is_aggregator("https://ca.indeed.com/viewjob?jk=1")
    assert is_aggregator("https://wellfound.com/jobs/1")
    assert not is_aggregator("https://boards.greenhouse.io/acme/jobs/1")


def test_title_matching_is_tolerant_but_not_reckless():
    assert titles_match("Data Analyst Intern", "Data Analyst Intern (Fall 2026)")
    assert titles_match("Senior Backend Engineer", "Backend Engineer")
    assert not titles_match("Data Analyst", "Sales Representative")


@pytest.mark.asyncio
async def test_ats_url_is_already_canonical():
    res = await resolve(discovery_url="https://boards.greenhouse.io/acme/jobs/1",
                        title="Data Analyst", company_name="Acme", http=object())
    assert res.status is ResolutionStatus.ALREADY_CANONICAL
    assert res.usable_as_canonical


@pytest.mark.asyncio
async def test_unresolved_aggregator_link_is_never_promoted():
    """The critical rule: a third-party link must not become canonical."""
    res = await resolve(discovery_url="https://www.linkedin.com/jobs/view/9",
                        title="Data Analyst", company_name="Acme", http=object(),
                        candidate_boards=[])
    assert res.status is ResolutionStatus.UNRESOLVED
    assert not res.usable_as_canonical

    fields = apply_resolution(
        {"canonical_application_url": "https://www.linkedin.com/jobs/view/9",
         "official_source_url": "https://www.linkedin.com/jobs/view/9",
         "source_priority": 1},
        res,
    )
    assert fields["canonical_application_url"] is None
    assert fields["official_source_url"] is None
    assert fields["source_priority"] == 3            # demoted to aggregator
    assert fields["inbox_category"] == "manual_review"
    assert fields["discovery_url"] == "https://www.linkedin.com/jobs/view/9"


@pytest.mark.asyncio
async def test_resolution_finds_the_official_posting(monkeypatch):
    """Third-party discovery resolves to the employer's own board."""
    from app.schemas.connector import ConnectorResult, RawJob

    class FakeBoard:
        key = "greenhouse"
        source_priority = 1

        async def fetch(self, source, http, since=None):
            return ConnectorResult(raw_jobs=[
                RawJob(source_job_id="1", title="Data Analyst Intern (Fall 2026)",
                       canonical_application_url="https://boards.greenhouse.io/acme/jobs/1",
                       source_status="open"),
            ])

    monkeypatch.setattr("app.connectors.registry.get_connector",
                        lambda key: FakeBoard())

    res = await resolve(discovery_url="https://www.linkedin.com/jobs/view/9",
                        title="Data Analyst Intern", company_name="Acme",
                        http=object(), candidate_boards=[("greenhouse", "acme")])
    assert res.status is ResolutionStatus.RESOLVED
    assert res.canonical_url == "https://boards.greenhouse.io/acme/jobs/1"
    assert res.verified_open is True

    fields = apply_resolution({"source_priority": 3}, res)
    assert fields["canonical_application_url"] == "https://boards.greenhouse.io/acme/jobs/1"
    assert fields["source_priority"] == 1            # promoted to first-party
    assert fields["discovery_url"] == "https://www.linkedin.com/jobs/view/9"


@pytest.mark.asyncio
async def test_closed_at_source_is_reported_not_hidden(monkeypatch):
    from app.schemas.connector import ConnectorResult, RawJob

    class ClosedBoard:
        key = "greenhouse"
        source_priority = 1

        async def fetch(self, source, http, since=None):
            return ConnectorResult(raw_jobs=[
                RawJob(source_job_id="1", title="Data Analyst Intern",
                       canonical_application_url="https://boards.greenhouse.io/acme/jobs/1",
                       source_status="closed"),
            ])

    monkeypatch.setattr("app.connectors.registry.get_connector",
                        lambda key: ClosedBoard())

    res = await resolve(discovery_url="https://www.linkedin.com/jobs/view/9",
                        title="Data Analyst Intern", company_name="Acme",
                        http=object(), candidate_boards=[("greenhouse", "acme")])
    assert res.status is ResolutionStatus.CLOSED_AT_SOURCE
    fields = apply_resolution({}, res)
    assert fields["source_status"] == "closed"
    assert fields["current_status"] == "position_closed"


def test_registry_exposes_all_implemented_connectors():
    for key in ("greenhouse", "lever", "ashby", "smartrecruiters", "workday",
                "oracle_orc", "jsonld", "sitemap", "user_import", "generic_ats"):
        assert get_connector(key) is not None


# ------------------------------------------------------------------- Workday

@pytest.mark.asyncio
async def test_workday_pagination_survives_total_zero_on_later_pages():
    """Workday reports `total` only on page 1; later pages report 0.

    Trusting it per-page stopped paging after two pages and silently lost almost
    the entire board (TD: 40 of 1815 postings). Regression guard.
    """
    from app.connectors.workday import WorkdayConnector

    PAGE = 20
    TOTAL = 95

    class FakeWorkday:
        def __init__(self):
            self.calls = 0

        async def post_json(self, url, *, json, headers=None):
            offset = json["offset"]
            remaining = max(0, TOTAL - offset)
            n = min(PAGE, remaining)
            self.calls += 1
            postings = [
                {"title": f"Job {offset + i}",
                 "externalPath": f"/job/x/{offset + i}",
                 "bulletFields": [f"R_{offset + i}"],
                 "locationsText": "Toronto, Ontario",
                 "postedOn": "Posted 3 Days Ago"}
                for i in range(n)
            ]
            # total only on the first page — exactly what the real API does
            return 200, {"jobPostings": postings,
                         "total": TOTAL if offset == 0 else 0}, {}

    http = FakeWorkday()
    res = await WorkdayConnector().fetch(
        SourceConfig(connector_key="workday", external_id="acme", display_name="Acme",
                     config={"tenant": "acme", "wd": 3, "site": "External"}),
        http,
    )
    assert len(res.raw_jobs) == TOTAL, f"collected {len(res.raw_jobs)} of {TOTAL}"
    assert res.diagnostics["reported_total"] == TOTAL
    assert res.raw_jobs[0].canonical_application_url.startswith(
        "https://acme.wd3.myworkdayjobs.com/en-US/External/job/"
    )


@pytest.mark.asyncio
async def test_workday_respects_max_pages_cap():
    """Never crawl an entire enterprise board in one pass."""
    from app.connectors.workday import WorkdayConnector

    class Endless:
        async def post_json(self, url, *, json, headers=None):
            off = json["offset"]
            return 200, {"jobPostings": [
                {"title": f"J{off + i}", "externalPath": f"/job/{off + i}",
                 "bulletFields": [f"R{off + i}"]} for i in range(20)
            ], "total": 100000 if off == 0 else 0}, {}

    res = await WorkdayConnector().fetch(
        SourceConfig(connector_key="workday", external_id="a", display_name="a",
                     config={"tenant": "a", "wd": 3, "site": "S", "max_pages": 3}),
        Endless(),
    )
    assert len(res.raw_jobs) == 60
    assert res.diagnostics["pages_capped"] is True
