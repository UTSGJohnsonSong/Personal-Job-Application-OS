"""Discover which real Canadian employers have a reachable first-party board.

Success is measured in verified employers and real postings, not in connector
count. For each employer we try token variants across the four LIVE connectors
and record what actually answered.

Output: a JSON registry of verified boards + a coverage report.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

from app.connectors.ashby import AshbyConnector
from app.connectors.greenhouse import GreenhouseConnector
from app.connectors.http import HttpClient
from app.connectors.lever import LeverConnector
from app.connectors.workday import WorkdayConnector
from app.schemas.connector import SourceConfig

# Canadian / Canada-hiring employers relevant to this candidate.
EMPLOYERS = """
Cohere Shopify Wealthsimple Ada Clio 1Password Hootsuite Jobber Wave Koho Borrowell
Waabi Tenstorrent Xanadu SanctuaryAI DeepGenomics BenchSci Layer6 Deeplite Signal1
Coveo Lightspeed Nuvei OpenText Kinaxis Geotab Ecobee Axonify D2L Thinkific
Vidyard Bench Float Neo Financial Dapper Labs Faire Ritual Drop Properly
Verafin Introhive Mapsted ApplyDigital Points Cyclica Phenomic BlueDot
Untether Vena Solutions Vidyard Certn Symend Trulioo Zafin Q4 Inc Mejuri
Loopio Rubikloud Integrate.ai Element AI Blue J Legal Kira Systems
Stripe Databricks Notion Figma Instacart DoorDash Cloudflare Datadog MongoDB
Snowflake Confluent HashiCorp Twilio Coinbase Plaid Brex Ramp Vanta Retool
Sourcegraph Supabase Vercel Linear Perplexity OpenAI Anthropic Deepgram
AssemblyAI ElevenLabs Harvey Sierra Glean Abridge Cursor Replit Modal Baseten
Runway Character Neon PlanetScale Railway Render Clerk Resend Inngest
Samsara Verkada Nuro Scale Anduril Discord Grammarly Duolingo Reddit Pinterest
Lyft Flexport Affirm Robinhood SoFi Gusto Rippling Deel Asana Dropbox Miro
Atlassian GitLab Sentry LaunchDarkly Amplitude Segment Fivetran Hex Benchling
""".split()

# Workday tenants: (label, tenant, wd pod, candidate site ids)
WORKDAY_CANDIDATES = [
    ("TD", "td", 3, ["TD_Bank_Careers"]),
    ("BMO", "bmo", 3, ["External"]),
    ("CIBC", "cibc", 3, ["search"]),
    ("Manulife", "manulife", 3, ["MFCJH_Jobs"]),
    ("Sun Life", "sunlife", 3, ["Experienced"]),
    ("RBC", "rbc", 3, ["RBCEXTERNAL", "External", "Careers", "RBC_External"]),
    ("RBC", "rbc", 1, ["RBCEXTERNAL", "External"]),
    ("Scotiabank", "scotiabank", 3, ["Scotiabank_Careers", "External", "Careers"]),
    ("Telus", "telus", 3, ["careers", "External", "TELUS_Careers"]),
    ("Loblaw", "loblaw", 3, ["External", "Careers"]),
    ("Rogers", "rogers", 3, ["External", "Careers"]),
    ("Bell", "bce", 3, ["External", "Careers"]),
    ("Shopify", "shopify", 5, ["External", "Careers"]),
    ("Thomson Reuters", "thomsonreuters", 5, ["External", "Careers"]),
    ("CPPIB", "cppib", 3, ["External", "Careers"]),
    ("OMERS", "omers", 3, ["External", "Careers"]),
    ("Canada Life", "canadalife", 3, ["External", "Careers"]),
    ("Intact", "intact", 3, ["External", "Careers"]),
    ("Aviva", "aviva", 3, ["External", "Careers"]),
    ("Definity", "definity", 3, ["External", "Careers"]),
    ("UHN", "uhn", 3, ["External", "Careers"]),
    ("SickKids", "sickkids", 3, ["External", "Careers"]),
]


def tokens_for(name: str) -> list[str]:
    """Plausible board tokens for an employer name."""
    base = name.lower()
    compact = re.sub(r"[^a-z0-9]", "", base)
    hyphen = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return list(dict.fromkeys([compact, hyphen, base]))


CANADA = re.compile(r"(toronto|canada|ontario|vancouver|montr|waterloo|ottawa|calgary|"
                    r"edmonton|halifax|winnipeg|kitchener|mississauga)", re.I)
GTA = re.compile(r"(toronto|mississauga|brampton|markham|vaughan|scarborough|etobicoke|"
                 r"north york|richmond hill|oakville|burlington|pickering|ajax|gta)", re.I)
REMOTE = re.compile(r"\bremote\b", re.I)
TECHY = re.compile(
    r"(software|backend|back-end|front-?end|full ?stack|data|analytics|analyst|"
    r"machine learning|\bml\b|\bai\b|platform|infrastructure|devops|cloud|product|"
    r"engineer|developer|scientist|business intelligence|\bbi\b|research)", re.I)


async def try_board(http, conn, key, token) -> dict | None:
    try:
        res = await conn.fetch(
            SourceConfig(connector_key=key, external_id=token, display_name=token), http
        )
    except Exception:
        return None
    if not res.raw_jobs:
        return None
    return {"connector": key, "token": token, "jobs": res.raw_jobs}


async def main() -> None:
    outdir = Path(sys.argv[1])
    sem = asyncio.Semaphore(8)
    connectors = [("greenhouse", GreenhouseConnector()), ("lever", LeverConnector()),
                  ("ashby", AshbyConnector())]

    verified: list[dict] = []
    attempted = 0

    async with HttpClient(max_retries=1, timeout=25) as http:
        async def guarded(conn, key, token):
            async with sem:
                return await try_board(http, conn, key, token)

        tasks = []
        meta = []
        for employer in EMPLOYERS:
            for token in tokens_for(employer):
                for key, conn in connectors:
                    tasks.append(guarded(conn, key, token))
                    meta.append((employer, key, token))
        attempted = len(tasks)
        results = await asyncio.gather(*tasks)

        seen: set[tuple[str, str]] = set()
        for (employer, key, token), r in zip(meta, results):
            if not r:
                continue
            if (key, token) in seen:
                continue
            seen.add((key, token))
            verified.append({"employer": employer, **r})

        # Workday tenants
        wd = WorkdayConnector()
        for label, tenant, pod, sites in WORKDAY_CANDIDATES:
            for site in sites:
                attempted += 1
                cfg = SourceConfig(
                    connector_key="workday", external_id=tenant, display_name=label,
                    config={"tenant": tenant, "wd": pod, "site": site,
                            "company_name": label},
                )
                try:
                    res = await wd.fetch(cfg, http)
                except Exception:
                    continue
                if res.raw_jobs:
                    verified.append({"employer": label, "connector": "workday",
                                     "token": f"{tenant}.wd{pod}/{site}",
                                     "jobs": res.raw_jobs,
                                     "config": {"tenant": tenant, "wd": pod, "site": site}})
                    break

    # ---------------- metrics ----------------
    per_connector: dict[str, dict] = {}
    registry: list[dict] = []
    all_hashes: set[str] = set()
    duplicates = 0
    closed = 0
    missing_link = 0

    for v in verified:
        key = v["connector"]
        m = per_connector.setdefault(key, {
            "employers": 0, "open_jobs": 0, "canada": 0, "gta": 0,
            "remote_ca": 0, "techy": 0, "closed": 0, "no_link": 0,
        })
        m["employers"] += 1
        for j in v["jobs"]:
            loc = (j.locations[0].raw_text if j.locations else "") or ""
            m["open_jobs"] += 1
            if j.source_status not in ("open", "updated"):
                m["closed"] += 1
                closed += 1
            if not j.canonical_application_url:
                m["no_link"] += 1
                missing_link += 1
            is_ca = bool(CANADA.search(loc))
            if is_ca:
                m["canada"] += 1
            if GTA.search(loc):
                m["gta"] += 1
            if REMOTE.search(loc) and is_ca:
                m["remote_ca"] += 1
            if TECHY.search(j.title):
                m["techy"] += 1
            h = j.content_hash or ""
            if h and h in all_hashes:
                duplicates += 1
            all_hashes.add(h)

        registry.append({
            "employer": v["employer"], "connector": key, "token": v["token"],
            "config": v.get("config"), "job_count": len(v["jobs"]),
            "canada_count": sum(1 for j in v["jobs"]
                                if CANADA.search((j.locations[0].raw_text
                                                  if j.locations else "") or "")),
        })

    (outdir / "board_registry.json").write_text(
        json.dumps(sorted(registry, key=lambda r: (-r["canada_count"], r["employer"])),
                   indent=2), encoding="utf-8")

    lines = ["SOURCE COVERAGE REPORT", "=" * 96, ""]
    lines.append(f"Board attempts: {attempted}   verified boards: {len(verified)}   "
                 f"success rate: {len(verified) / attempted:.1%}")
    lines.append("")
    hdr = (f"{'CONNECTOR':<16}{'EMPLOYERS':>10}{'OPEN JOBS':>11}{'CANADA':>9}"
           f"{'GTA':>7}{'CA REMOTE':>11}{'TECH/DATA':>11}{'CLOSED':>8}{'NO LINK':>9}")
    lines.append(hdr)
    lines.append("-" * len(hdr))
    tot = dict.fromkeys(
        ["employers", "open_jobs", "canada", "gta", "remote_ca", "techy", "closed", "no_link"], 0)
    for key in ("greenhouse", "lever", "ashby", "workday"):
        m = per_connector.get(key)
        if not m:
            lines.append(f"{key:<16}{'0':>10}{'—':>11}")
            continue
        lines.append(f"{key:<16}{m['employers']:>10}{m['open_jobs']:>11}{m['canada']:>9}"
                     f"{m['gta']:>7}{m['remote_ca']:>11}{m['techy']:>11}"
                     f"{m['closed']:>8}{m['no_link']:>9}")
        for k in tot:
            tot[k] += m[k]
    lines.append("-" * len(hdr))
    lines.append(f"{'TOTAL':<16}{tot['employers']:>10}{tot['open_jobs']:>11}"
                 f"{tot['canada']:>9}{tot['gta']:>7}{tot['remote_ca']:>11}"
                 f"{tot['techy']:>11}{tot['closed']:>8}{tot['no_link']:>9}")
    lines.append("")
    lines.append(f"Duplicate postings detected (content hash): {duplicates}")
    lines.append(f"Closed postings: {closed}    Postings with no application link: {missing_link}")
    lines.append("")
    lines.append("VERIFIED BOARDS (Canada-heavy first)")
    lines.append("-" * 96)
    for r in sorted(registry, key=lambda r: -r["canada_count"])[:60]:
        lines.append(f"  {r['employer']:<22} {r['connector']:<14} {str(r['token'])[:30]:<30} "
                     f"jobs={r['job_count']:<5} canada={r['canada_count']}")

    (outdir / "coverage_report.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"verified boards: {len(verified)} / attempts {attempted}")
    print(f"total open jobs: {tot['open_jobs']}  canada: {tot['canada']}  gta: {tot['gta']}")


if __name__ == "__main__":
    asyncio.run(main())
