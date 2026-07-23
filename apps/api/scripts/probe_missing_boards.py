"""Probe the 28 companies whose profiles.py `boards=` entry was never carried
into app/company/sources.py, so sync_verified.py has been silently skipping
them (same bug class fixed for 10 tier S/A companies in d1cdc1a — this is the
rest of the list). Nothing here is registered as VERIFIED until this script
confirms it against the live board.

Usage: python scripts/probe_missing_boards.py /path/to/out/dir
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


def wd(tenant: str, site: str, pod: int = 3, pages: int = 10) -> dict:
    return {"tenant": tenant, "wd": pod, "site": site, "max_pages": pages}


def sf(base: str, name: str) -> dict:
    return {"base_url": base, "company_name": name, "max_pages": 10}


# From profiles.py `boards=` (the declared-but-never-registered ones), carried
# over 1:1, plus the workday site guesses already sitting in app/sources/boards.py
# for the four bank/insurer tenants.
GUESSES: list[tuple[str, str, str, dict | None]] = [
    ("benchsci", "lever", "benchsci", None),
    ("benchling", "greenhouse", "benchling", None),
    ("waabi", "lever", "waabi", None),
    ("tenstorrent", "greenhouse", "tenstorrent", None),
    ("plaid", "greenhouse", "plaid", None),
    ("bmo", "workday", "bmo", wd("bmo", "External")),
    ("cibc", "workday", "cibc", wd("cibc", "search")),
    ("manulife", "workday", "manulife", wd("manulife", "MFCJH_Jobs")),
    ("manulife", "workday", "manulife", wd("manulife", "External")),
    ("sunlife", "workday", "sunlife", wd("sunlife", "Experienced")),
    ("d2l", "greenhouse", "d2l", None),
    ("docebo", "greenhouse", "docebo", None),
    ("achievers", "lever", "achievers", None),
    ("trulioo", "ashby", "trulioo", None),
    ("faire", "greenhouse", "faire", None),
    ("openai", "ashby", "openai", None),
    ("anthropic", "greenhouse", "anthropic", None),
    ("databricks", "greenhouse", "databricks", None),
    ("snowflake", "ashby", "snowflake", None),
    ("mongodb", "greenhouse", "mongodb", None),
    ("datadog", "greenhouse", "datadog", None),
    ("cloudflare", "greenhouse", "cloudflare", None),
    ("figma", "greenhouse", "figma", None),
    ("notion", "ashby", "notion", None),
    ("coinbase", "greenhouse", "coinbase", None),
    ("visa", "smartrecruiters", "Visa", None),
    ("marsdd", "bamboohr", "marsdd", None),
    ("hootsuite", "greenhouse", "hootsuite", None),
    ("cityoftoronto", "successfactors", "https://jobs.toronto.ca/jobsatcity",
     sf("https://jobs.toronto.ca/jobsatcity", "City of Toronto")),
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
    (out / "missing_boards_probe.json").write_text(
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
    print(f"\n{len(results)} guesses -> {len(hits)} answered, {len(solid)} credible")
    print(f"companies with zero working guess: {sorted(never_hit)}")
    print("\nCanadian student roles found right now:")
    for r in solid:
        for s in r["student_roles"]:
            print(f"  [{r['key']}] {s['title']}  ({s['location']})")


if __name__ == "__main__":
    asyncio.run(main())
