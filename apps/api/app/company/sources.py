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
