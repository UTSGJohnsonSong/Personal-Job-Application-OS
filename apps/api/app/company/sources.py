"""Official source registry — step 7 of the pipeline.

For every company in the registry, where do its postings actually come from?

The important rule here is that a company we cannot reach automatically is NOT
removed. It is recorded as MANUAL_ONLY with its official careers URL and enters
the manual application queue. The previous design let connector coverage decide
which employers existed at all, which is how Amazon, Google, Microsoft and RBC
came to be missing from a ranking that called itself complete.

Every VERIFIED entry below was probed against the live board and the observed
counts recorded with the date. Nothing here is asserted from a naming
convention: slug-guessing produced four hits across twenty-three companies, two
of which were different companies sharing a slug.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

PROBED_ON = "2026-07-23"


class SourceStatus(StrEnum):
    VERIFIED = "verified"          # probed, answered, counts recorded
    MANUAL_ONLY = "manual_only"    # reachable by a human, not by us
    SEARCHING = "searching"        # candidate endpoint identified, not confirmed
    PARTIAL = "partial"            # board answers but is not the whole board


@dataclass(frozen=True)
class OfficialSource:
    company_key: str
    status: SourceStatus
    careers_url: str
    connector: str | None = None
    external_id: str | None = None
    config: dict = field(default_factory=dict)
    # Observations from the probe. Absent when the status is not VERIFIED.
    observed_jobs: int | None = None
    observed_canada: int | None = None
    observed_student_canada: int | None = None
    note: str = ""
    probed_on: str = PROBED_ON

    @property
    def automatable(self) -> bool:
        return self.status in (SourceStatus.VERIFIED, SourceStatus.PARTIAL)


def _wd(tenant: str, site: str, pod: int = 3, pages: int = 25) -> dict:
    return {"tenant": tenant, "wd": pod, "site": site, "max_pages": pages}


def _sf(base: str, name: str, pages: int = 15) -> dict:
    return {"base_url": base, "company_name": name, "max_pages": pages}


# ---------------------------------------------------------------------------
# Verified on 2026-07-23 against the live board.
# ---------------------------------------------------------------------------
VERIFIED: list[OfficialSource] = [
    OfficialSource(
        "thomsonreuters", SourceStatus.VERIFIED,
        "https://careers.thomsonreuters.com",
        "workday", "thomsonreuters", _wd("thomsonreuters", "External_Career_Site", pod=5),
        observed_jobs=486, observed_canada=68, observed_student_canada=0,
        note="Collected all 486 of 486 reported. This board omits locationsText "
             "and puts the location in bulletFields, which the connector "
             "previously mis-read as the job id — it yielded 32 jobs and zero "
             "Canadian roles until that was fixed."),
    OfficialSource(
        "neofinancial", SourceStatus.VERIFIED, "https://www.neofinancial.com/careers",
        "ashby", "neofinancial",
        observed_jobs=110, observed_canada=100, observed_student_canada=0,
        note="Almost entirely Canadian hiring."),
    OfficialSource(
        "eqbank", SourceStatus.VERIFIED, "https://www.eqbank.ca/about-us/careers",
        "lever", "eqbank",
        observed_jobs=71, observed_canada=67, observed_student_canada=2,
        note="Canadian student roles open now, including Intern, CloudOps (Toronto)."),
    OfficialSource(
        "instacart", SourceStatus.VERIFIED, "https://instacart.careers",
        "greenhouse", "instacart",
        observed_jobs=127, observed_canada=54, observed_student_canada=0),
    OfficialSource(
        "hopper", SourceStatus.VERIFIED, "https://www.hopper.com/careers",
        "ashby", "hopper",
        observed_jobs=100, observed_canada=29, observed_student_canada=0),
    OfficialSource(
        "janeapp", SourceStatus.VERIFIED, "https://jane.app/careers",
        "ashby", "jane",
        observed_jobs=27, observed_canada=23, observed_student_canada=0),
    OfficialSource(
        "bankofcanada", SourceStatus.VERIFIED, "https://careers.bankofcanada.ca",
        "successfactors", "Bank of Canada",
        _sf("https://careers.bankofcanada.ca", "Bank of Canada"),
        observed_jobs=16, observed_canada=16, observed_student_canada=1,
        note="Small board, entirely Canadian. A PhD Internship (Ottawa) is open."),
    OfficialSource(
        "float", SourceStatus.VERIFIED, "https://www.floatfinancial.com/careers",
        "ashby", "float",
        observed_jobs=12, observed_canada=12, observed_student_canada=0),
    OfficialSource(
        "wattpad", SourceStatus.VERIFIED, "https://www.wattpad.com/careers",
        "lever", "wattpad",
        observed_jobs=25, observed_canada=7, observed_student_canada=0),
    # --- tier S/A boards declared on the profile but not yet registered ---
    # These carried a `boards` entry in profiles.py, so the pool treated them
    # as verified, but they were never in this registry and so were never
    # synced. Probed 2026-07-23 and moved here so the sync actually fetches them.
    OfficialSource(
        "wealthsimple", SourceStatus.VERIFIED, "https://www.wealthsimple.com/careers",
        "ashby", "wealthsimple",
        observed_jobs=32, observed_canada=32, observed_student_canada=0,
        note="His number-one target. Entirely Canadian hiring."),
    OfficialSource(
        "cohere", SourceStatus.VERIFIED, "https://cohere.com/careers",
        "ashby", "cohere",
        observed_jobs=136, observed_canada=44, observed_student_canada=3,
        note="Three Canadian student/co-op roles open now."),
    OfficialSource(
        "stripe", SourceStatus.VERIFIED, "https://stripe.com/jobs",
        "greenhouse", "stripe",
        observed_jobs=523, observed_canada=49, observed_student_canada=1),
    OfficialSource(
        "stackadapt", SourceStatus.VERIFIED, "https://www.stackadapt.com/careers",
        "greenhouse", "stackadapt",
        observed_jobs=95, observed_canada=56, observed_student_canada=0),
    OfficialSource(
        "pointclickcare", SourceStatus.VERIFIED,
        "https://pointclickcare.com/careers",
        "lever", "pointclickcare",
        observed_jobs=92, observed_canada=49, observed_student_canada=0),
    OfficialSource(
        "1password", SourceStatus.VERIFIED, "https://1password.com/careers",
        "ashby", "1password",
        observed_jobs=66, observed_canada=47, observed_student_canada=0),
    OfficialSource(
        "geotab", SourceStatus.VERIFIED, "https://www.geotab.com/careers",
        "greenhouse", "geotab",
        observed_jobs=102, observed_canada=35, observed_student_canada=0),
    OfficialSource(
        "jobber", SourceStatus.VERIFIED, "https://careers.getjobber.com",
        "ashby", "jobber",
        observed_jobs=46, observed_canada=23, observed_student_canada=0),
    OfficialSource(
        "scotiabank", SourceStatus.VERIFIED, "https://jobs.scotiabank.com",
        "successfactors", "Scotiabank",
        _sf("https://jobs.scotiabank.com", "Scotiabank"),
        observed_jobs=300, observed_canada=188, observed_student_canada=1,
        note="Velocity student stream posts here; one co-op role open at probe."),
    # --- newly added companies, probed 2026-07-23 on the JSON boards ---
    OfficialSource(
        "pinterest", SourceStatus.VERIFIED, "https://www.pinterestcareers.com",
        "greenhouse", "pinterest",
        observed_jobs=193, observed_canada=15, observed_student_canada=0,
        note="Toronto data/ML roles among a mostly-US board."),
    OfficialSource(
        "spotify", SourceStatus.VERIFIED, "https://www.lifeatspotify.com",
        "lever", "spotify",
        observed_jobs=108, observed_canada=5, observed_student_canada=0),
    OfficialSource(
        "later", SourceStatus.VERIFIED, "https://later.com/careers",
        "greenhouse", "later",
        observed_jobs=65, observed_canada=12, observed_student_canada=0),
    OfficialSource(
        "relayfi", SourceStatus.VERIFIED, "https://relayfi.com/careers",
        "ashby", "relay",
        observed_jobs=25, observed_canada=8, observed_student_canada=0),
    OfficialSource(
        "kabam", SourceStatus.VERIFIED, "https://www.kabam.com/careers",
        "lever", "kabam",
        observed_jobs=16, observed_canada=16, observed_student_canada=0,
        note="Vancouver studio, entirely Canadian board."),
    # --- profiles.py `boards=` entries that were declared but never carried
    # into this registry, so sync_verified.py silently skipped all 28 of them.
    # Same bug class as the block above; probed 2026-07-23 with
    # scripts/probe_missing_boards.py rather than assumed from the slug.
    OfficialSource(
        "waabi", SourceStatus.VERIFIED, "https://waabi.ai/careers",
        "lever", "waabi",
        observed_jobs=58, observed_canada=32, observed_student_canada=2,
        note="2026 PhD Research Scientist intern and a research co-op open."),
    OfficialSource(
        "tenstorrent", SourceStatus.VERIFIED, "https://tenstorrent.com/careers",
        "greenhouse", "tenstorrent",
        observed_jobs=127, observed_canada=43, observed_student_canada=0),
    OfficialSource(
        "databricks", SourceStatus.VERIFIED,
        "https://www.databricks.com/company/careers",
        "greenhouse", "databricks",
        observed_jobs=800, observed_canada=24, observed_student_canada=0),
    OfficialSource(
        "mongodb", SourceStatus.VERIFIED, "https://www.mongodb.com/careers",
        "greenhouse", "mongodb",
        observed_jobs=401, observed_canada=23, observed_student_canada=0),
    OfficialSource(
        "d2l", SourceStatus.VERIFIED, "https://www.d2l.com/careers/",
        "greenhouse", "d2l",
        observed_jobs=27, observed_canada=19, observed_student_canada=0),
    OfficialSource(
        "achievers", SourceStatus.VERIFIED, "https://www.achievers.com/careers/",
        "lever", "achievers",
        observed_jobs=23, observed_canada=19, observed_student_canada=1,
        note="A Content Co-op is open in Toronto."),
    OfficialSource(
        "trulioo", SourceStatus.VERIFIED, "https://www.trulioo.com/careers",
        "ashby", "trulioo",
        observed_jobs=25, observed_canada=12, observed_student_canada=0),
    OfficialSource(
        "faire", SourceStatus.VERIFIED, "https://www.faire.com/careers",
        "greenhouse", "faire",
        observed_jobs=66, observed_canada=13, observed_student_canada=0),
    OfficialSource(
        "snowflake", SourceStatus.VERIFIED, "https://careers.snowflake.com",
        "ashby", "snowflake",
        observed_jobs=411, observed_canada=9, observed_student_canada=0),
    OfficialSource(
        "coinbase", SourceStatus.VERIFIED, "https://www.coinbase.com/careers",
        "greenhouse", "coinbase",
        observed_jobs=154, observed_canada=9, observed_student_canada=0),
    OfficialSource(
        "hootsuite", SourceStatus.VERIFIED, "https://hootsuite.com/careers",
        "greenhouse", "hootsuite",
        observed_jobs=18, observed_canada=8, observed_student_canada=0),
    OfficialSource(
        "anthropic", SourceStatus.VERIFIED, "https://www.anthropic.com/careers",
        "greenhouse", "anthropic",
        observed_jobs=409, observed_canada=7, observed_student_canada=0),
    OfficialSource(
        "datadog", SourceStatus.VERIFIED, "https://www.datadoghq.com/careers/",
        "greenhouse", "datadog",
        observed_jobs=419, observed_canada=2, observed_student_canada=0),
    OfficialSource(
        "benchsci", SourceStatus.VERIFIED, "https://www.benchsci.com/careers",
        "lever", "benchsci",
        observed_jobs=1, observed_canada=1, observed_student_canada=0,
        note="Board only carries a single 'General Interest' Toronto req at "
             "probe time — quiet, not a bad slug (title reads as a real "
             "BenchSci posting, not a stray same-slug company)."),
    OfficialSource(
        "marsdd", SourceStatus.VERIFIED, "https://www.marsdd.com/careers/",
        "bamboohr", "marsdd",
        observed_jobs=3, observed_canada=3, observed_student_canada=0,
        note="Small nonprofit board, all Toronto roles."),
    OfficialSource(
        "cityoftoronto", SourceStatus.VERIFIED,
        "https://jobs.toronto.ca/jobsatcity",
        "successfactors", "https://jobs.toronto.ca/jobsatcity",
        _sf("https://jobs.toronto.ca/jobsatcity", "City of Toronto"),
        observed_jobs=68, observed_canada=48, observed_student_canada=0),
    # US-headquartered boards with little to no Canadian presence, kept
    # VERIFIED (not dropped) because a probe answered honestly; the near-zero
    # Canada count is the true state of the board, not a connector failure.
    OfficialSource(
        "openai", SourceStatus.VERIFIED, "https://openai.com/careers",
        "ashby", "openai",
        observed_jobs=735, observed_canada=0, observed_student_canada=0,
        note="No Canadian postings on the board at probe time."),
    OfficialSource(
        "cloudflare", SourceStatus.VERIFIED, "https://www.cloudflare.com/careers/",
        "greenhouse", "cloudflare",
        observed_jobs=268, observed_canada=0, observed_student_canada=0),
    OfficialSource(
        "figma", SourceStatus.VERIFIED, "https://www.figma.com/careers/",
        "greenhouse", "figma",
        observed_jobs=173, observed_canada=0, observed_student_canada=0),
    OfficialSource(
        "notion", SourceStatus.VERIFIED, "https://www.notion.com/careers",
        "ashby", "notion",
        observed_jobs=138, observed_canada=0, observed_student_canada=0),
]

# ---------------------------------------------------------------------------
# Answers, but is demonstrably not the company's whole hiring surface.
# Recorded as PARTIAL so nothing downstream reads absence as evidence.
# ---------------------------------------------------------------------------
PARTIAL: list[OfficialSource] = [
    OfficialSource(
        "sap", SourceStatus.PARTIAL, "https://jobs.sap.com",
        "successfactors", "SAP", _sf("https://jobs.sap.com", "SAP", pages=40),
        observed_jobs=867, observed_canada=4, observed_student_canada=0,
        note="867 postings but only 4 Canadian, all sales. SAP's Waterloo and "
             "Vancouver co-op intake is not on this board — its early-talent "
             "programme is published separately and still needs locating. "
             "Second known gap: the connector recovers a location for only 17 "
             "of 866 postings here, while reading 16 of 16 on the Bank of "
             "Canada's SuccessFactors site, so this is site-specific markup we "
             "do not parse yet. Treat SAP's Canadian counts as a floor."),
    OfficialSource(
        "td", SourceStatus.PARTIAL, "https://jobs.td.com",
        "workday", "td",
        _wd("td", "TD_Bank_Careers", pages=15),
        observed_jobs=300, observed_canada=105, observed_student_canada=0,
        note="Workday reports 1,795 postings; the page cap collects the first "
             "300, so its Canadian count is a floor. Raising max_pages would "
             "capture more but the co-op stream is seasonal and worth a "
             "targeted search rather than a full crawl."),
    # Workday boards from the profiles.py `boards=` gap (see VERIFIED block
    # above) that hit the page cap exactly (10 pages * 20/page = 200) during
    # the probe, so the true Canadian count is a floor, not the total.
    OfficialSource(
        "bmo", SourceStatus.PARTIAL, "https://jobs.bmo.com",
        "workday", "bmo", _wd("bmo", "External", pages=25),
        observed_jobs=200, observed_canada=122, observed_student_canada=2,
        note="Probe hit the 200-job page cap; two Fall 2026 co-op postings "
             "(Finance Analyst, Data Scientist) found already."),
    OfficialSource(
        "cibc", SourceStatus.PARTIAL, "https://jobs.cibc.com",
        "workday", "cibc", _wd("cibc", "search", pages=25),
        observed_jobs=200, observed_canada=152, observed_student_canada=0,
        note="Probe hit the 200-job page cap; heavily Canadian board."),
    OfficialSource(
        "manulife", SourceStatus.PARTIAL, "https://www.manulife.ca/careers.html",
        "workday", "manulife", _wd("manulife", "MFCJH_Jobs", pages=25),
        observed_jobs=200, observed_canada=15, observed_student_canada=1,
        note="Probe hit the 200-job page cap. site='External' refuses; "
             "'MFCJH_Jobs' is the working site. A Fall Co-op 2026 AI "
             "Enablement role is open in Toronto."),
    OfficialSource(
        "sunlife", SourceStatus.PARTIAL, "https://www.sunlife.ca/en/careers/",
        "workday", "sunlife", _wd("sunlife", "Experienced", pages=25),
        observed_jobs=200, observed_canada=44, observed_student_canada=0,
        note="Probe hit the 200-job page cap."),
]

# ---------------------------------------------------------------------------
# Reachable by a human only. These are NOT downgraded and NOT removed; they go
# to the manual queue with the URL a person would actually open.
# ---------------------------------------------------------------------------
MANUAL_ONLY: list[OfficialSource] = [
    OfficialSource("amazon", SourceStatus.MANUAL_ONLY,
                   "https://www.amazon.jobs/en/teams/internships-for-students",
                   note="Own ATS. Canadian SDE co-op cohorts post here; the "
                        "student portal is the correct entry point."),
    OfficialSource("microsoft", SourceStatus.MANUAL_ONLY,
                   "https://careers.microsoft.com/students",
                   note="Own ATS with a separate students surface."),
    OfficialSource("google", SourceStatus.MANUAL_ONLY,
                   "https://www.google.com/about/careers/applications/students",
                   note="Own ATS. Waterloo and Toronto intake."),
    OfficialSource("shopify", SourceStatus.MANUAL_ONLY,
                   "https://www.shopify.com/careers/interns",
                   note="Own ATS; the Engineering and Data internship stream is "
                        "a distinct application flow."),
    OfficialSource("rbc", SourceStatus.MANUAL_ONLY, "https://jobs.rbc.com",
                   note="Phenom, not Workday or SuccessFactors — both were "
                        "probed and refused. Amplify and Early Talent are "
                        "separate programme pages."),
    OfficialSource("nvidia", SourceStatus.MANUAL_ONLY,
                   "https://www.nvidia.com/en-us/about-nvidia/careers/university-recruiting/"),
    OfficialSource("amd", SourceStatus.MANUAL_ONLY,
                   "https://careers.amd.com/careers-home/jobs?keywords=co-op",
                   note="Markham Fall co-op cohorts."),
    OfficialSource("intuit", SourceStatus.MANUAL_ONLY,
                   "https://jobs.intuit.com/students",
                   note="Toronto Fall software co-op stream."),
    OfficialSource("capitalone", SourceStatus.MANUAL_ONLY,
                   "https://www.capitalonecareers.ca",
                   note="Separate Canadian careers domain."),
    OfficialSource("amex", SourceStatus.MANUAL_ONLY, "https://www.americanexpress.com/en-ca/careers/"),
    OfficialSource("mastercard", SourceStatus.MANUAL_ONLY, "https://careers.mastercard.com"),
    OfficialSource("salesforce", SourceStatus.MANUAL_ONLY,
                   "https://www.salesforce.com/company/careers/university-recruiting/"),
    OfficialSource("ibm", SourceStatus.MANUAL_ONLY, "https://www.ibm.com/careers/ca-en/early-career/"),
    OfficialSource("autodesk", SourceStatus.MANUAL_ONLY,
                   "https://www.autodesk.com/careers/university"),
    OfficialSource("uber", SourceStatus.MANUAL_ONLY, "https://www.uber.com/us/en/careers/",
                   note="The smartrecruiters board that answered had one posting "
                        "and is not Uber's."),
    OfficialSource("clio", SourceStatus.MANUAL_ONLY, "https://www.clio.com/about/careers/"),
    OfficialSource("lightspeed", SourceStatus.MANUAL_ONLY,
                   "https://careers.lightspeedhq.com",
                   note="The ashby/lightspeed board that answered had four "
                        "postings and is a different company."),
    OfficialSource("kinaxis", SourceStatus.MANUAL_ONLY, "https://careers.kinaxis.com"),
    OfficialSource("ssense", SourceStatus.MANUAL_ONLY, "https://www.ssense.com/en-ca/careers"),
    OfficialSource("mila", SourceStatus.MANUAL_ONLY, "https://mila.quebec/en/careers"),
    OfficialSource("vectorinstitute", SourceStatus.MANUAL_ONLY,
                   "https://vectorinstitute.ai/careers/",
                   note="Its internships are published as programme pages, not "
                        "as an ATS feed."),
    OfficialSource("fidelity", SourceStatus.MANUAL_ONLY,
                   "https://www.fidelitycareers.ca",
                   note="He has an existing relationship here; the manual route "
                        "is the right one regardless of automation."),
    OfficialSource("bioadvance", SourceStatus.MANUAL_ONLY, "",
                   note="No careers surface located yet. Named as a first choice, "
                        "so this needs a human check rather than another probe."),
    # profiles.py declared a `boards=` guess for each of these; probed
    # 2026-07-23 and the guess did not hold up (empty response or a board
    # that looks like a different company/tenant), so they go to manual
    # rather than being registered on unverified faith.
    OfficialSource("visa", SourceStatus.MANUAL_ONLY,
                   "https://corporate.visa.com/en/careers.html",
                   note="The smartrecruiters/Visa board that answered had two "
                        "postings (Austin, Bengaluru) with no Canadian roles — "
                        "reads as a regional or stale tenant, not Visa's real "
                        "board. Needs a better slug or a different connector."),
    OfficialSource("benchling", SourceStatus.MANUAL_ONLY,
                   "https://www.benchling.com/careers",
                   note="Guessed greenhouse/benchling returned empty."),
    OfficialSource("docebo", SourceStatus.MANUAL_ONLY,
                   "https://www.docebo.com/company/careers/",
                   note="Guessed greenhouse/docebo returned empty."),
    OfficialSource("plaid", SourceStatus.MANUAL_ONLY,
                   "https://plaid.com/careers/",
                   note="Guessed greenhouse/plaid returned empty."),
]

ALL_SOURCES: list[OfficialSource] = [*VERIFIED, *PARTIAL, *MANUAL_ONLY]
BY_COMPANY: dict[str, OfficialSource] = {s.company_key: s for s in ALL_SOURCES}


def coverage() -> dict[str, int]:
    out: dict[str, int] = {s.value: 0 for s in SourceStatus}
    for s in ALL_SOURCES:
        out[s.status.value] += 1
    return out


def automatable_sources() -> list[OfficialSource]:
    return [s for s in ALL_SOURCES if s.automatable]


def manual_queue() -> list[OfficialSource]:
    """Companies a human has to apply to. Present in the system, not dropped."""
    return [s for s in ALL_SOURCES if s.status is SourceStatus.MANUAL_ONLY]
