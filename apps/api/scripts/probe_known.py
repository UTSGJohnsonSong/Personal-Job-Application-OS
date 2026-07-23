"""Verify specific, hand-supplied ATS guesses for named companies.

Slug guessing failed for the large employers, as expected: they run their own
ATS, and the boards it did find were false positives (an "ashby/lightspeed"
board with 4 postings is not Lightspeed's careers site). So this file carries
deliberate guesses, one per company, and only reports what actually answers.

Nothing here invents a source. A company with no verified board keeps its
official careers URL and goes to the manual queue.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

from app.connectors.ashby import AshbyConnector
from app.connectors.bamboohr import BambooHrConnector
from app.connectors.greenhouse import GreenhouseConnector
from app.connectors.http import HttpClient
from app.connectors.lever import LeverConnector
from app.connectors.smartrecruiters import SmartRecruitersConnector
from app.connectors.successfactors import SuccessFactorsConnector
from app.connectors.workday import WorkdayConnector
from app.schemas.connector import SourceConfig

CONN = {
    "greenhouse": GreenhouseConnector(), "lever": LeverConnector(),
    "ashby": AshbyConnector(), "workday": WorkdayConnector(),
    "successfactors": SuccessFactorsConnector(), "bamboohr": BambooHrConnector(),
    "smartrecruiters": SmartRecruitersConnector(),
}

CANADA = re.compile(
    r"(toronto|canada|ontario|vancouver|montr|ottawa|waterloo|calgary|mississauga|"
    r"edmonton|halifax|winnipeg|kitchener|burnaby|markham|brampton|\bON\b|\bBC\b)", re.I)
STUDENT = re.compile(
    r"\b(intern|internship|co-?op|student|campus|new ?grad|early career|rotational|"
    r"apprentice|PEY|work term)\b", re.I)


def wd(tenant: str, site: str, pod: int = 3, pages: int = 8) -> dict:
    return {"tenant": tenant, "wd": pod, "site": site, "max_pages": pages}


def sf(base: str, name: str) -> dict:
    return {"base_url": base, "company_name": name, "max_pages": 10}


# (company key, connector, external_id, config) — deliberate guesses, not derived.
GUESSES: list[tuple[str, str, str, dict | None]] = [
    # Canadian banks and insurers already known to run Workday.
    ("rbc", "workday", "rbc", wd("rbc", "RBCEXTERNAL")),
    ("rbc", "successfactors", "RBC", sf("https://jobs.rbc.com", "RBC")),
    # Thomson Reuters runs Workday on pod 5.
    ("thomsonreuters", "workday", "thomsonreuters",
     wd("thomsonreuters", "External_Career_Site", pod=5)),
    ("thomsonreuters", "workday", "thomsonreuters", wd("thomsonreuters", "External", pod=5)),
    # SAP owns SuccessFactors, so its own board is the reference implementation.
    ("sap", "successfactors", "SAP", sf("https://jobs.sap.com", "SAP")),
    ("salesforce", "workday", "salesforce", wd("salesforce", "External_Career_Site")),
    ("mastercard", "workday", "mastercard", wd("mastercard", "CorporateCareers")),
    ("mastercard", "workday", "mastercard", wd("mastercard", "External")),
    ("amex", "workday", "aexp", wd("aexp", "External")),
    ("capitalone", "workday", "capitalone", wd("capitalone", "External")),
    ("intuit", "workday", "intuit", wd("intuit", "External")),
    ("autodesk", "workday", "autodesk", wd("autodesk", "Ext")),
    ("autodesk", "workday", "autodesk", wd("autodesk", "External")),
    ("dayforce", "workday", "ceridian", wd("ceridian", "External")),
    ("nvidia", "workday", "nvidia", wd("nvidia", "NVIDIAExternalCareerSite")),
    ("amd", "workday", "amd", wd("amd", "External")),
    ("uber", "workday", "uber", wd("uber", "External")),
    ("ibm", "workday", "ibm", wd("ibm", "External")),
    # Canadian tech on the JSON boards.
    ("clio", "greenhouse", "clio", None),
    ("clio", "lever", "clio", None),
    ("kinaxis", "greenhouse", "kinaxis", None),
    ("kinaxis", "workday", "kinaxis", wd("kinaxis", "kinaxis_careers")),
    ("lightspeed", "greenhouse", "lightspeedcommerce", None),
    ("lightspeed", "lever", "lightspeedhq", None),
    ("ssense", "lever", "ssense", None),
    ("ssense", "greenhouse", "ssense", None),
    ("shopify", "greenhouse", "shopify", None),
    ("shopify", "lever", "shopify", None),
    ("vectorinstitute", "bamboohr", "vectorinstitute", None),
    ("mila", "bamboohr", "mila", None),
    ("mila", "lever", "mila", None),
    ("bankofcanada", "successfactors", "Bank of Canada",
     sf("https://careers.bankofcanada.ca", "Bank of Canada")),
    ("fidelity", "workday", "fmr", wd("fmr", "FidelityCareers")),
    ("questrade", "lever", "questrade", None),
    ("questrade", "greenhouse", "questrade", None),
    ("wattpad", "lever", "wattpad", None),
    ("ada", "lever", "ada", None),
    ("ada", "greenhouse", "ada", None),
    ("interac", "successfactors", "Interac", sf("https://careers.interac.ca", "Interac")),
    ("loblawdigital", "workday", "loblaw", wd("loblaw", "External")),
    ("descartes", "greenhouse", "descartes", None),
    ("blackberry", "workday", "blackberry", wd("blackberry", "External")),
    ("opentext", "successfactors", "OpenText",
     sf("https://careers.opentext.com", "OpenText")),
    ("cppinvestments", "workday", "cppib", wd("cppib", "External")),
    ("otpp", "workday", "otpp", wd("otpp", "External")),
    ("omers", "workday", "omers", wd("omers", "External")),
    ("manulife", "workday", "manulife", wd("manulife", "MFCJH_Jobs")),
    ("sickkids", "successfactors", "SickKids",
     sf("https://careers.sickkids.ca", "SickKids")),
    ("uhn", "successfactors", "UHN", sf("https://careers.uhn.ca", "UHN")),
    ("eqbank", "lever", "eqbank", None),
    ("eqbank", "greenhouse", "equitablebank", None),
    ("instacart", "greenhouse", "instacart", None),
    ("applyboard", "lever", "applyboard", None),
    ("applyboard", "greenhouse", "applyboard", None),
    ("janeapp", "lever", "janeapp", None),
    ("janeapp", "ashby", "jane", None),
    ("mindbridge", "lever", "mindbridge", None),
    ("mindbridge", "greenhouse", "mindbridgeai", None),
    ("pockethealth", "lever", "pockethealth", None),
    ("talai", "lever", "tali", None),
    ("seamlessmd", "lever", "seamlessmd", None),
    ("signal1", "lever", "signal1", None),
    ("float", "ashby", "float", None),
    ("neofinancial", "ashby", "neofinancial", None),
    ("hopper", "ashby", "hopper", None),
]

# A board answering with a handful of postings for a large employer is almost
# certainly a different company with the same slug.
SUSPICIOUS_BELOW = 10


async def one(http, sem, key, conn_key, ext, cfg):
    async with sem:
        try:
            res = await CONN[conn_key].fetch(SourceConfig(
                connector_key=conn_key, external_id=ext,
                display_name=key, config=cfg or {}), http)
        except Exception as exc:
            return {"key": key, "connector": conn_key, "external_id": ext,
                    "ok": False, "error": type(exc).__name__}
    jobs = res.raw_jobs
    if not jobs:
        return {"key": key, "connector": conn_key, "external_id": ext,
                "ok": False, "error": "empty"}
    locs = [(j.locations[0].raw_text if j.locations else "") or "" for j in jobs]
    ca = sum(1 for x in locs if CANADA.search(x))
    stu_ca = [j for j, x in zip(jobs, locs, strict=False)
              if STUDENT.search(j.title) and CANADA.search(x)]
    return {
        "key": key, "connector": conn_key, "external_id": ext, "config": cfg,
        "ok": True, "jobs": len(jobs), "canada": ca,
        "students": sum(1 for j in jobs if STUDENT.search(j.title)),
        "students_canada": len(stu_ca),
        "suspicious": len(jobs) < SUSPICIOUS_BELOW,
        "student_roles": [
            {"title": j.title,
             "location": (j.locations[0].raw_text if j.locations else ""),
             "url": j.canonical_application_url}
            for j in stu_ca[:6]],
    }


async def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(8)
    async with HttpClient(max_retries=1, timeout=30) as http:
        results = await asyncio.gather(
            *[one(http, sem, *g) for g in GUESSES])

    hits = [r for r in results if r["ok"]]
    hits.sort(key=lambda r: (-r["canada"], -r["jobs"]))
    (out / "known_probe.json").write_text(json.dumps(results, indent=2),
                                          encoding="utf-8")

    print(f"{'COMPANY':<18}{'CONNECTOR':>16}{'ID':>22}{'JOBS':>7}{'CA':>6}{'STU-CA':>8}")
    print("-" * 78)
    for r in hits:
        flag = "  <- suspicious, verify" if r["suspicious"] else ""
        print(f"{r['key'][:17]:<18}{r['connector']:>16}{str(r['external_id'])[:21]:>22}"
              f"{r['jobs']:>7}{r['canada']:>6}{r['students_canada']:>8}{flag}")

    solid = [r for r in hits if not r["suspicious"]]
    keys = {r["key"] for r in solid}
    print(f"\n{len(results)} guesses -> {len(hits)} answered, {len(solid)} credible, "
          f"covering {len(keys)} companies")
    print("\nCanadian student roles found right now:")
    for r in solid:
        for s in r["student_roles"]:
            print(f"  [{r['key']}] {s['title']}  ({s['location']})")


if __name__ == "__main__":
    asyncio.run(main())
