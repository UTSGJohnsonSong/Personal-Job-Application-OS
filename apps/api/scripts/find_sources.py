"""Find an official application source for every company already in the registry.

Direction matters. An earlier sweep probed ATS vendors and then treated whatever
answered as the company universe, which silently defined the candidate set as
"employers using the vendors we support" — Amazon, Google, Microsoft and RBC
were never even eligible to be ranked.

This runs the other way: the registry is fixed, and for each company we look for
its source. A company we cannot reach is NOT dropped. It is recorded as
`manual_only`, which puts it in the manual application queue rather than
removing it from the system.

Usage:  python scripts/find_sources.py <out_dir> [--tier S,A]
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

from app.company.profiles import ALL_PROFILES, CompanyProfile
from app.connectors.ashby import AshbyConnector
from app.connectors.bamboohr import BambooHrConnector
from app.connectors.greenhouse import GreenhouseConnector
from app.connectors.http import HttpClient
from app.connectors.lever import LeverConnector
from app.connectors.smartrecruiters import SmartRecruitersConnector
from app.connectors.workday import WorkdayConnector
from app.schemas.connector import SourceConfig

CANADA = re.compile(
    r"(toronto|canada|ontario|vancouver|montr|ottawa|waterloo|calgary|mississauga|"
    r"edmonton|halifax|winnipeg|kitchener|burnaby|markham|brampton|\bON\b|\bBC\b|"
    r"\bAB\b|\bQC\b)", re.I)
STUDENT = re.compile(
    r"\b(intern|internship|co-?op|student|campus|new ?grad|early career|rotational|"
    r"apprentice|PEY|work term)\b", re.I)

# Cheap JSON boards: one GET each, so every candidate token is affordable.
SIMPLE = [
    ("greenhouse", GreenhouseConnector()),
    ("lever", LeverConnector()),
    ("ashby", AshbyConnector()),
]

# Workday tenants are guessable but the site id is not, so each needs a small
# fan-out over the handful of names Workday deployments actually use.
WD_SITES = ["External", "Careers", "External_Career_Site", "careers", "search"]


def tokens(name: str) -> list[str]:
    """Candidate board slugs. Ordered cheapest-first; the first hit wins."""
    base = name.lower()
    base = re.sub(r"\b(inc|ltd|limited|corp|corporation|group|canada|the)\b", "", base)
    compact = re.sub(r"[^a-z0-9]", "", base)
    hyphen = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    first = compact.split()[0] if compact.split() else compact
    return [t for t in dict.fromkeys([compact, hyphen, first]) if len(t) > 2]


async def probe(http, connector_key, connector, external_id, config, label):
    try:
        res = await connector.fetch(SourceConfig(
            connector_key=connector_key, external_id=external_id,
            display_name=label, config=config or {}), http)
    except Exception:
        return None
    jobs = res.raw_jobs
    if not jobs:
        return None
    locs = [(j.locations[0].raw_text if j.locations else "") or "" for j in jobs]
    canada = sum(1 for x in locs if CANADA.search(x))
    students = [j for j in jobs if STUDENT.search(j.title)]
    student_ca = sum(1 for j, x in zip(jobs, locs, strict=False)
                     if STUDENT.search(j.title) and CANADA.search(x))
    return {
        "connector": connector_key,
        "external_id": external_id,
        "config": config,
        "jobs": len(jobs),
        "canada": canada,
        "students": len(students),
        "students_canada": student_ca,
        "sample_student_roles": [
            {"title": j.title,
             "location": (j.locations[0].raw_text if j.locations else ""),
             "url": j.canonical_application_url}
            for j in students[:5]
        ],
    }


async def find_for(http, sem, p: CompanyProfile) -> dict:
    """Try every cheap avenue for one company. First non-empty board wins."""
    async def guarded(*args):
        async with sem:
            return await probe(http, *args)

    attempts: list[tuple] = []
    for token in tokens(p.name):
        for key, conn in SIMPLE:
            attempts.append((key, conn, token, None, p.name))
    # Workday: only worth trying for employers large enough to run one.
    if p.depth >= 2:
        for token in tokens(p.name)[:2]:
            for site in WD_SITES[:3]:
                attempts.append((
                    "workday", WorkdayConnector(), token,
                    {"tenant": token, "wd": 3, "site": site, "max_pages": 3},
                    p.name))
    if p.depth >= 2:
        attempts.append(("smartrecruiters", SmartRecruitersConnector(),
                         p.name.replace(" ", ""), None, p.name))
    if p.depth <= 2:
        for token in tokens(p.name)[:2]:
            attempts.append(("bamboohr", BambooHrConnector(), token, None, p.name))

    results = await asyncio.gather(*[guarded(*a) for a in attempts])
    hits = [r for r in results if r]
    # Prefer the board that actually shows Canadian hiring; a tenant that
    # answers with 4 US roles is a worse answer than no answer.
    hits.sort(key=lambda r: (-r["canada"], -r["students_canada"], -r["jobs"]))
    return {
        "key": p.key,
        "name": p.name,
        "tier": p.personal_tier,
        "value": round(p.value_score, 1),
        "access": round(p.access_score, 1),
        "attempts": len(attempts),
        "status": "found" if hits else "manual_only",
        "best": hits[0] if hits else None,
        "other_hits": hits[1:3],
    }


async def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    wanted = None
    if len(sys.argv) > 2 and sys.argv[2].startswith("--tier"):
        wanted = set(sys.argv[2].split("=")[1].split(","))

    targets = [p for p in ALL_PROFILES
               if not p.boards and (wanted is None or p.personal_tier in wanted)]
    order = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
    targets.sort(key=lambda p: (order[p.personal_tier], -p.personal_score))
    print(f"searching sources for {len(targets)} companies without one\n")

    sem = asyncio.Semaphore(10)
    async with HttpClient(max_retries=1, timeout=25) as http:
        found = await asyncio.gather(*[find_for(http, sem, p) for p in targets])

    (out / "source_search.json").write_text(
        json.dumps(found, indent=2), encoding="utf-8")

    ok = [r for r in found if r["status"] == "found"]
    ca = [r for r in ok if r["best"]["canada"] > 0]
    stu = [r for r in ok if r["best"]["students_canada"] > 0]
    print(f"{'COMPANY':<26}{'TIER':>5}{'CONNECTOR':>16}{'JOBS':>7}{'CA':>6}{'STU-CA':>8}")
    print("-" * 70)
    for r in sorted(ok, key=lambda r: (order[r["tier"]], -r["best"]["canada"])):
        b = r["best"]
        print(f"{r['name'][:25]:<26}{r['tier']:>5}{b['connector']:>16}"
              f"{b['jobs']:>7}{b['canada']:>6}{b['students_canada']:>8}")

    print(f"\nfound {len(ok)}/{len(targets)}   with Canadian roles {len(ca)}   "
          f"with Canadian student roles {len(stu)}")
    print(f"manual_only (kept, not dropped): {len(targets) - len(ok)}")


if __name__ == "__main__":
    asyncio.run(main())
