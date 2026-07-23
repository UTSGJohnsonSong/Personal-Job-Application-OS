"""Broad discovery across the employers that actually matter in Canada.

The previous sweep was a hand-typed tech list and therefore skewed American and
missed whole categories. This one walks the major Canadian employer segments —
banks, insurers, telecom, retail, energy, pensions, consulting, health,
universities, government and crown corporations — and tries every connector we
have, not just the three JSON boards.

Nothing here claims to be exhaustive: Canada has tens of thousands of
employers. It aims to cover the ones a Toronto CS/DS student would realistically
target.
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

# --------------------------------------------------------------- employer sets
BANKS_INSURERS = """RBC TD BMO Scotiabank CIBC NationalBank Desjardins
Manulife SunLife CanadaLife GreatWestLife Intact Aviva Definity Wawanesa
Cooperators EquitableLife IAFinancial FairfaxFinancial Onex Brookfield""".split()

PENSIONS = """CPPIB OMERS OTPP HOOPP PSP IMCO AIMCo BCI""".split()

TELECOM_MEDIA = """Bell Rogers Telus Shaw Quebecor CBC Corus Thomson Reuters""".split()

RETAIL_CONSUMER = """Loblaw CanadianTire Sobeys Metro Shopify LuluLemon Aritzia
RestaurantBrands Couchetard Dollarama HudsonsBay Indigo Roots Mejuri""".split()

ENERGY_INDUSTRIAL = """Enbridge Suncor Cenovus TCEnergy Fortis Hydro One OPG
Bombardier CAE Magna Linamar ATS Nutrien Teck Barrick Agnico""".split()

CONSULTING_PRO = """Deloitte KPMG PwC EY Accenture McKinsey BCG Bain
CGI Capgemini Infosys Cognizant Slalom ThoughtWorks""".split()

HEALTH = """UHN SickKids SinaiHealth SunnybrookHSC UnityHealth
TrilliumHealth WilliamOsler Michael Garron Ontario Health CAMH""".split()

UNIVERSITIES = """UofT TorontoMetropolitan YorkUniversity Waterloo McMaster
Queens Western Ottawa McGill UBC Guelph Carleton Seneca Humber""".split()

GOV_CROWN = """CityOfToronto OntarioPublicService Metrolinx TTC LCBO
CanadaPost VIARail NavCanada BankOfCanada CRA StatCan""".split()

TECH_CANADA = """Cohere Waabi Wealthsimple Ada Clio 1Password Hootsuite Jobber
Wave Koho Borrowell Tenstorrent Xanadu SanctuaryAI DeepGenomics BenchSci
Coveo Lightspeed Nuvei OpenText Kinaxis Geotab Ecobee Axonify D2L Thinkific
Vidyard Float Neo DapperLabs Faire Ritual Properly Verafin Introhive Trulioo
Certn Symend Zafin Q4 Loopio VenaSolutions Clearco League Maple Felix
PointClickCare Intelex Achievers Docebo Magnet Forme StackAdapt AdGear
Sampler Blockthrough Eventbase Bitmaker Shakepay Newton Netcoins""".split()

TECH_GLOBAL_CA = """Stripe Databricks Snowflake MongoDB Datadog Cloudflare
Instacart DoorDash Lyft Pinterest Reddit Samsara Verkada Affirm Robinhood
Brex Ramp Notion Figma Asana Dropbox GitLab Twilio Coinbase Plaid Rippling
Deel Vanta Retool Sourcegraph Supabase Vercel Linear OpenAI Anthropic
Perplexity Harvey Glean Nuro Duolingo Grammarly Discord Flexport Gusto
SoFi HashiCorp Confluent Sentry Amplitude Segment Fivetran Hex Benchling
Scale Anduril Miro Atlassian LaunchDarkly""".split()

ALL_EMPLOYERS = list(dict.fromkeys(
    BANKS_INSURERS + PENSIONS + TELECOM_MEDIA + RETAIL_CONSUMER
    + ENERGY_INDUSTRIAL + CONSULTING_PRO + HEALTH + UNIVERSITIES
    + GOV_CROWN + TECH_CANADA + TECH_GLOBAL_CA
))

# Workday tenants worth trying (tenant, pod, candidate site ids).
WORKDAY = [
    ("td", 3, ["TD_Bank_Careers"]), ("bmo", 3, ["External"]),
    ("cibc", 3, ["search"]), ("manulife", 3, ["MFCJH_Jobs"]),
    ("sunlife", 3, ["Experienced"]), ("rbc", 3, ["RBCEXTERNAL", "External"]),
    ("scotiabank", 3, ["Scotiabank_Careers", "External"]),
    ("telus", 3, ["careers", "External"]), ("bell", 3, ["External", "Careers"]),
    ("rogers", 3, ["External", "Careers"]), ("loblaw", 3, ["External"]),
    ("canadiantire", 3, ["External", "Careers"]),
    ("thomsonreuters", 5, ["External", "Careers"]),
    ("cppib", 3, ["External"]), ("omers", 3, ["External"]),
    ("otpp", 3, ["External"]), ("intact", 3, ["External"]),
    ("aviva", 3, ["External"]), ("definity", 3, ["External"]),
    ("canadalife", 3, ["External"]), ("enbridge", 3, ["External"]),
    ("suncor", 3, ["External"]), ("hydroone", 3, ["External"]),
    ("opg", 3, ["External"]), ("bombardier", 3, ["External"]),
    ("magna", 3, ["External"]), ("nutrien", 3, ["External"]),
    ("deloitte", 3, ["External"]), ("kpmg", 3, ["External"]),
    ("pwc", 3, ["External"]), ("ey", 3, ["External"]),
    ("accenture", 3, ["External"]), ("cgi", 3, ["External"]),
    ("uhn", 3, ["External"]), ("sickkids", 3, ["External"]),
    ("utoronto", 3, ["External", "Careers"]),
    ("yorku", 3, ["External"]), ("uwaterloo", 3, ["External"]),
    ("mcmaster", 3, ["External"]), ("queensu", 3, ["External"]),
    ("lcbo", 3, ["External"]), ("canadapost", 3, ["External"]),
    ("shopify", 5, ["External"]),
]

# SuccessFactors RMK career sites (verified pattern: /tile-search-results/).
SUCCESSFACTORS = [
    ("City of Toronto", "https://jobs.toronto.ca/jobsatcity"),
    ("Scotiabank", "https://jobs.scotiabank.com"),
    ("RBC", "https://jobs.rbc.com"),
    ("Bell", "https://jobs.bell.ca"),
    ("Telus", "https://careers.telus.com"),
    ("Metrolinx", "https://careers.metrolinx.com"),
    ("Loblaw", "https://careers.loblaw.ca"),
    ("Canadian Tire", "https://jobs.canadiantire.ca"),
    ("Sobeys", "https://jobs.sobeys.com"),
    ("Enbridge", "https://careers.enbridge.com"),
]

BAMBOO = ["marsdd", "vectorinstitute", "communitech", "dmz"]
SMARTRECRUITERS = ["Deloitte", "Bosch", "Ubisoft", "McDonalds", "Visa", "Square"]


def tokens_for(name: str) -> list[str]:
    base = name.lower()
    return list(dict.fromkeys([
        re.sub(r"[^a-z0-9]", "", base),
        re.sub(r"[^a-z0-9]+", "-", base).strip("-"),
    ]))


CANADA = re.compile(r"(toronto|canada|ontario|\bON\b|\bBC\b|\bAB\b|\bQC\b|vancouver|"
                    r"montr|ottawa|waterloo|calgary|mississauga|edmonton|halifax|"
                    r"winnipeg|kitchener|burnaby|markham|brampton)", re.I)
STUDENT = re.compile(r"\b(intern|internship|co-?op|student|campus|new ?grad|"
                     r"early career|rotational|apprentice|summer 20\d\d|fall 20\d\d)\b",
                     re.I)


async def probe(http, key, conn, external_id, config, label):
    try:
        res = await conn.fetch(SourceConfig(
            connector_key=key, external_id=external_id, display_name=label,
            config=config or {}), http)
    except Exception:
        return None
    if not res.raw_jobs:
        return None
    jobs = res.raw_jobs
    locs = [(j.locations[0].raw_text if j.locations else "") or "" for j in jobs]
    students = [j for j in jobs if STUDENT.search(j.title)]
    student_ca = [j for j, x in zip(jobs, locs)
                  if STUDENT.search(j.title) and CANADA.search(x)]
    return {
        "employer": label, "connector": key, "external_id": external_id,
        "config": config, "jobs": len(jobs),
        "empty_location": sum(1 for x in locs if not x.strip()),
        "canada": sum(1 for x in locs if CANADA.search(x)),
        "students": len(students), "students_canada": len(student_ca),
        "student_titles": [
            {"title": j.title,
             "loc": (j.locations[0].raw_text if j.locations else ""),
             "url": j.canonical_application_url}
            for j in students[:12]
        ],
    }


async def main() -> None:
    out = Path(sys.argv[1])
    sem = asyncio.Semaphore(8)
    found: list[dict] = []
    attempts = 0

    simple = [("greenhouse", GreenhouseConnector()), ("lever", LeverConnector()),
              ("ashby", AshbyConnector())]

    async with HttpClient(max_retries=1, timeout=30) as http:
        async def guarded(*a):
            async with sem:
                return await probe(http, *a)

        tasks, meta = [], []
        for name in ALL_EMPLOYERS:
            for tok in tokens_for(name):
                for key, conn in simple:
                    tasks.append(guarded(key, conn, tok, None, name))
                    meta.append((key, tok))
        for tenant, pod, sites in WORKDAY:
            for site in sites:
                tasks.append(guarded("workday", WorkdayConnector(), tenant,
                                     {"tenant": tenant, "wd": pod, "site": site,
                                      "max_pages": 25}, tenant))
                meta.append(("workday", f"{tenant}/{site}"))
        for label, base in SUCCESSFACTORS:
            tasks.append(guarded("successfactors", SuccessFactorsConnector(), label,
                                 {"base_url": base, "company_name": label,
                                  "max_pages": 12}, label))
            meta.append(("successfactors", base))
        for tok in BAMBOO:
            tasks.append(guarded("bamboohr", BambooHrConnector(), tok, None, tok))
            meta.append(("bamboohr", tok))
        for tok in SMARTRECRUITERS:
            tasks.append(guarded("smartrecruiters", SmartRecruitersConnector(), tok,
                                 None, tok))
            meta.append(("smartrecruiters", tok))

        attempts = len(tasks)
        results = await asyncio.gather(*tasks)

    seen: set[tuple[str, str]] = set()
    for (key, tok), r in zip(meta, results):
        if not r or (key, tok) in seen:
            continue
        seen.add((key, tok))
        found.append(r)

    (out / "canada_discovery.json").write_text(json.dumps(found, indent=2),
                                               encoding="utf-8")
    tot_jobs = sum(r["jobs"] for r in found)
    tot_ca = sum(r["canada"] for r in found)
    tot_stu = sum(r["students"] for r in found)
    tot_stu_ca = sum(r["students_canada"] for r in found)
    empty = sum(r["empty_location"] for r in found)

    print(f"attempts {attempts}  verified boards {len(found)}")
    print(f"jobs {tot_jobs}  canada {tot_ca}  empty-location {empty} "
          f"({empty / max(tot_jobs, 1):.0%})")
    print(f"student/co-op {tot_stu}   of which Canada-matched {tot_stu_ca}")
    print(f"employers with Canadian student roles: "
          f"{sum(1 for r in found if r['students_canada'])}")
    by_conn: dict[str, int] = {}
    for r in found:
        by_conn[r["connector"]] = by_conn.get(r["connector"], 0) + 1
    print("boards by connector:", by_conn)


if __name__ == "__main__":
    asyncio.run(main())
