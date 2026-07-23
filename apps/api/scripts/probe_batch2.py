"""Second wave of ATS probing against the ~186 companies with no source entry
at all (never had a `boards=` guess in profiles.py to begin with, unlike the
28 handled in probe_missing_boards.py). Same rule as always: nothing gets
registered from a slug guess alone, only from what a live probe confirms.

Usage: python scripts/probe_batch2.py /path/to/out/dir
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
    r"edmonton|halifax|winnipeg|kitchener|burnaby|markham|brampton|\bON\b|\bBC\b|"
    r"qu[ée]bec)", re.I)
STUDENT = re.compile(
    r"\b(intern|internship|co-?op|student|campus|new ?grad|early career|rotational|"
    r"apprentice|PEY|work term)\b", re.I)


def wd(tenant: str, site: str, pod: int = 3, pages: int = 10) -> dict:
    return {"tenant": tenant, "wd": pod, "site": site, "max_pages": pages}


def sf(base: str, name: str) -> dict:
    return {"base_url": base, "company_name": name, "max_pages": 10}


GUESSES: list[tuple[str, str, str, dict | None]] = [
    # Bank capital-markets arms: try the parent bank's own tenant with a
    # markets-specific site, since these divisions often share IT with retail.
    ("tdsecurities", "workday", "td", wd("td", "TD_Bank_Careers", pages=10)),
    ("rbccm", "workday", "rbc", wd("rbc", "RBCEXTERNAL", pages=10)),
    ("bmocm", "workday", "bmo", wd("bmo", "External", pages=10)),
    ("nationalbank", "workday", "nbc", wd("nbc", "External")),
    ("nationalbank", "successfactors", "National Bank",
     sf("https://jobs.nbc.ca", "National Bank")),
    # Big US/global tech with a Canadian presence.
    ("bloomberg", "workday", "bloomberg", wd("bloomberg", "Bloomberg_Careers")),
    ("lseg", "workday", "lseg", wd("lseg", "External")),
    ("tiktok", "smartrecruiters", "TikTok", None),
    ("meta", "workday", "meta", wd("meta", "Meta_Careers")),
    ("oracle", "oracle_orc", "oracle", {"site": "https://careers.oracle.com"}),
    ("servicenow", "workday", "servicenow", wd("servicenow", "Careers")),
    ("cisco", "workday", "cisco", wd("cisco", "Cisco_Careers")),
    ("workday", "workday", "workday", wd("workday", "Ext")),
    ("block", "greenhouse", "block", None),
    ("block", "greenhouse", "squareinc", None),
    ("twilio2", "greenhouse", "twilio", None),
    ("doordash", "greenhouse", "doordash", None),
    ("wayfair", "greenhouse", "wayfair", None),
    ("intel", "workday", "intel", wd("intel", "External")),
    ("qualcomm", "workday", "qualcomm", wd("qualcomm", "External")),
    ("unity", "greenhouse", "unity3d", None),
    ("morningstar", "workday", "morningstar", wd("morningstar", "External")),
    ("adobe", "workday", "adobe", wd("adobe", "external_experienced")),
    # Canadian mid-size SaaS.
    ("coveo", "greenhouse", "coveo", None),
    ("loopio", "lever", "loopio", None),
    ("vena", "lever", "venasolutions", None),
    ("q4", "lever", "q4", None),
    ("ecobee", "lever", "ecobee", None),
    ("vidyard", "lever", "vidyard", None),
    ("constellation", "greenhouse", "constellationsoftware", None),
    ("magnetforensics", "greenhouse", "magnetforensics", None),
    ("axonify", "lever", "axonify", None),
    ("klue", "lever", "klue", None),
    ("touchbistro", "greenhouse", "touchbistro", None),
    ("thinkific", "greenhouse", "thinkific", None),
    ("auvik", "lever", "auvik", None),
    ("miovision", "lever", "miovision", None),
    ("genetec", "greenhouse", "genetec", None),
    ("esentire", "lever", "esentire", None),
    ("bluecat", "lever", "bluecatnetworks", None),
    ("soti", "greenhouse", "soti", None),
    ("visier", "greenhouse", "visier", None),
    ("absolute", "greenhouse", "absolutesoftware", None),
    ("copperleaf", "lever", "copperleaf", None),
    ("dapperlabs", "greenhouse", "dapperlabs", None),
    ("introhive", "lever", "introhive", None),
    ("tealbook", "lever", "tealbook", None),
    ("roserocket", "lever", "roserocket", None),
    ("nulogy", "lever", "nulogy", None),
    ("assent", "greenhouse", "assentcompliance", None),
    ("certn", "lever", "certn", None),
    ("rangle", "lever", "rangle", None),
    ("clearpath", "lever", "clearpathrobotics", None),
    ("tophat", "greenhouse", "tophat", None),
    # Fintech.
    ("koho", "lever", "koho", None),
    ("nuvei", "greenhouse", "nuvei", None),
    ("borrowell", "lever", "borrowell", None),
    ("wave", "lever", "wave", None),
    ("clearco", "greenhouse", "clearco", None),
    ("shakepay", "lever", "shakepay", None),
    ("flinks", "lever", "flinks", None),
    ("arteriaai", "lever", "arteria", None),
    ("freshbooks", "greenhouse", "freshbooks", None),
    ("moneris", "successfactors", "Moneris", sf("https://jobs.moneris.com", "Moneris")),
    ("nestwealth", "lever", "nestwealth", None),
    ("conquest", "lever", "conquestplanning", None),
    ("brim", "lever", "brimfinancial", None),
    ("loopfin", "lever", "loop", None),
    ("caary", "lever", "caary", None),
    ("nesto", "greenhouse", "nesto", None),
    ("ratehub", "lever", "ratehub", None),
    ("tmx", "workday", "tmx", wd("tmx", "External")),
    ("questrade", "greenhouse", "questradefinancialgroup", None),
    ("interac", "greenhouse", "interac", None),
    # Health / health-AI.
    ("thinkresearch", "lever", "thinkresearch", None),
    ("pockethealth", "greenhouse", "pockethealth", None),
    ("bluedot", "greenhouse", "bluedot", None),
    ("deepgenomics", "greenhouse", "deepgenomics", None),
    ("alayacare", "lever", "alayacare", None),
    ("league", "greenhouse", "league", None),
    ("wellhealth", "greenhouse", "wellhealth", None),
    ("maple", "lever", "getmaple", None),
    ("dialogue", "greenhouse", "dialogue", None),
    ("fullscript", "greenhouse", "fullscript", None),
    ("telushealth", "workday", "telus", wd("telus", "TELUS_Careers")),
    ("medme", "lever", "medme", None),
    ("rocketdoctor", "lever", "rocketdoctor", None),
    ("uhn", "workday", "uhn", wd("uhn", "External")),
    ("sickkids", "workday", "sickkids", wd("sickkids", "External")),
    ("camh", "successfactors", "CAMH", sf("https://careers.camh.ca", "CAMH")),
    # Gaming.
    ("ubisoft", "smartrecruiters", "Ubisoft", None),
    ("ea", "workday", "ea", wd("ea", "Careers")),
    ("behaviour", "greenhouse", "behaviour", None),
    ("gameloft", "smartrecruiters", "Gameloft", None),
    ("eidos", "smartrecruiters", "SquareEnix", None),
    # Insurance.
    ("intact", "workday", "intact", wd("intact", "External")),
    ("definity", "workday", "definity", wd("definity", "External")),
    ("canadalife", "workday", "canadalife", wd("canadalife", "External")),
    ("cooperators", "successfactors", "Co-operators",
     sf("https://jobs.cooperators.ca", "Co-operators")),
    ("iafinancial", "workday", "ia", wd("ia", "External")),
    # Retail tech.
    ("canadiantire", "workday", "canadiantire", wd("canadiantire", "External")),
    ("lululemon", "workday", "lululemon", wd("lululemon", "lululemon")),
    ("aritzia", "workday", "aritzia", wd("aritzia", "External")),
    ("loblawdigital", "greenhouse", "loblawdigital", None),
    # Crown corps / pension funds.
    ("cppinvestments", "workday", "cppib", wd("cppib", "CPPIB_Careers")),
    ("otpp", "workday", "otpp", wd("otpp", "OTPP_Careers")),
    ("omers", "workday", "omers", wd("omers", "OMERS_Careers")),
    ("brookfield", "workday", "brookfield", wd("brookfield", "External")),
    ("statcan", "successfactors", "Statistics Canada",
     sf("https://www.statcan.gc.ca/en/employment", "Statistics Canada")),
    # Deep-tech / space.
    ("kepler", "lever", "kepler", None),
    ("mda", "workday", "mda", wd("mda", "External")),
    ("indexexchange", "lever", "indexexchange", None),
    ("snyk", "greenhouse", "snyk", None),
    ("cira", "bamboohr", "cira", None),
]

SUSPICIOUS_BELOW = 10


async def one(http, sem, key, conn_key, ext, cfg):
    async with sem:
        try:
            res = await CONN[conn_key].fetch(SourceConfig(
                connector_key=conn_key, external_id=ext,
                display_name=key, config=cfg or {}), http)
        except Exception as exc:
            return {"key": key, "connector": conn_key, "external_id": ext,
                    "config": cfg, "ok": False, "error": type(exc).__name__}
    jobs = res.raw_jobs
    if not jobs:
        return {"key": key, "connector": conn_key, "external_id": ext,
                "config": cfg, "ok": False, "error": "empty"}
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
        results = await asyncio.gather(*[one(http, sem, *g) for g in GUESSES])

    hits = [r for r in results if r["ok"]]
    hits.sort(key=lambda r: (-r["canada"], -r["jobs"]))
    (out / "batch2_probe.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")

    print(f"{'COMPANY':<16}{'CONNECTOR':>16}{'ID':>26}{'JOBS':>7}{'CA':>6}{'STU-CA':>8}")
    print("-" * 82)
    for r in hits:
        flag = "  <- suspicious, verify" if r["suspicious"] else ""
        print(f"{r['key'][:15]:<16}{r['connector']:>16}{str(r['external_id'])[:25]:>26}"
              f"{r['jobs']:>7}{r['canada']:>6}{r['students_canada']:>8}{flag}")

    tried_keys = {r["key"] for r in results}
    hit_keys = {r["key"] for r in hits}
    never_hit = tried_keys - hit_keys
    solid = [r for r in hits if not r["suspicious"]]
    print(f"\n{len(results)} guesses -> {len(hits)} answered, {len(solid)} credible, "
          f"covering {len({r['key'] for r in solid})} companies")
    print(f"companies with zero working guess: {sorted(never_hit - hit_keys)}")
    print("\nCanadian student roles found right now:")
    for r in solid:
        for s in r["student_roles"]:
            print(f"  [{r['key']}] {s['title']}  ({s['location']})")


if __name__ == "__main__":
    asyncio.run(main())
