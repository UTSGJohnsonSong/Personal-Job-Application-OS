"""Final company tiering across the broad Canadian employer set.

Every dimension is measured from the employer's own board (grade-A first-party
data). Two notes on honesty:

* The brand dimension is measured as GLOBAL HIRING FOOTPRINT — how many distinct
  countries/regions the employer is actively hiring in. That is a real, checkable
  proxy for reach; it is NOT consumer brand recognition, and it is labelled that
  way in the evidence text so nobody mistakes one for the other.
* Stability is measured as SUSTAINED HIRING VOLUME. A company posting hundreds of
  roles is demonstrably operating; it says nothing about its balance sheet. Weak
  evidence, recorded as weak (grade B).

Everything is personalised to this candidate: Canadian presence and student
hiring carry the weight, because that is what a Toronto co-op search needs.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

from app.company.intelligence import CompanyDimension as D
from app.company.intelligence import Evidence, SourceGrade, assess_company
from app.connectors.ashby import AshbyConnector
from app.connectors.bamboohr import BambooHrConnector
from app.connectors.greenhouse import GreenhouseConnector
from app.connectors.http import HttpClient
from app.connectors.lever import LeverConnector
from app.connectors.smartrecruiters import SmartRecruitersConnector
from app.connectors.successfactors import SuccessFactorsConnector
from app.connectors.workday import WorkdayConnector
from app.schemas.connector import SourceConfig

CONNECTORS = {
    "greenhouse": GreenhouseConnector(), "lever": LeverConnector(),
    "ashby": AshbyConnector(), "workday": WorkdayConnector(),
    "successfactors": SuccessFactorsConnector(), "bamboohr": BambooHrConnector(),
    "smartrecruiters": SmartRecruitersConnector(),
}

CANADA = re.compile(r"(toronto|canada|ontario|\bON\b|\bBC\b|\bAB\b|\bQC\b|vancouver|"
                    r"montr|ottawa|waterloo|calgary|mississauga|edmonton|halifax|"
                    r"winnipeg|kitchener|burnaby|markham|brampton|barrie)", re.I)
GTA = re.compile(r"(toronto|mississauga|brampton|markham|vaughan|scarborough|"
                 r"etobicoke|north york|richmond hill|oakville)", re.I)
STUDENT = re.compile(r"\b(intern|internship|co-?op|student|campus|new ?grad|"
                     r"early career|rotational|apprentice)\b", re.I)
TECH = re.compile(r"(software|backend|front-?end|full ?stack|data|analytics|analyst|"
                  r"machine learning|\bml\b|\bai\b|platform|infrastructure|devops|"
                  r"cloud|engineer|developer|scientist|product|technolog)", re.I)

COUNTRY_HINTS = [
    ("canada", CANADA), ("usa", re.compile(r"(united states|\bUS\b|\bUSA\b|california|"
     r"new york|texas|washington|seattle|boston|chicago|atlanta|austin|denver|"
     r"san francisco|nyc)", re.I)),
    ("uk", re.compile(r"(united kingdom|london|\bUK\b|england|manchester)", re.I)),
    ("eu", re.compile(r"(germany|france|paris|berlin|munich|amsterdam|netherlands|"
     r"spain|madrid|ireland|dublin|poland|warsaw|sweden|stockholm)", re.I)),
    ("apac", re.compile(r"(singapore|japan|tokyo|australia|sydney|india|bangalore|"
     r"hong kong|korea|seoul|china|shanghai|philippines|manila)", re.I)),
    ("latam", re.compile(r"(mexico|brazil|colombia|chile|peru|argentina|lima|"
     r"bogot|s.o paulo)", re.I)),
    ("mea", re.compile(r"(dubai|uae|israel|tel aviv|south africa|egypt|saudi)", re.I)),
]


def _ev(dim, value, summary, grade=SourceGrade.A):
    return Evidence(url="official_board", source_type="official_ats", grade=grade,
                    supports_dimension=dim, summary=summary, value=value)


def scale(n, full):
    return max(0.0, min(1.0, n / full))


async def analyse(http, row) -> dict | None:
    conn = CONNECTORS.get(row["connector"])
    if conn is None:
        return None
    try:
        res = await conn.fetch(SourceConfig(
            connector_key=row["connector"], external_id=row["external_id"],
            display_name=row["employer"], config=row.get("config") or {}), http)
    except Exception:
        return None
    jobs = res.raw_jobs
    if not jobs:
        return None

    locs = [(j.locations[0].raw_text if j.locations else "") or "" for j in jobs]
    canada = sum(1 for x in locs if CANADA.search(x))
    gta = sum(1 for x in locs if GTA.search(x))
    students = [j for j in jobs if STUDENT.search(j.title)]
    students_ca = [j for j, x in zip(jobs, locs, strict=False)
                   if STUDENT.search(j.title) and CANADA.search(x)]
    tech = sum(1 for j in jobs if TECH.search(j.title))
    depts = {(j.department or "").strip().lower() for j in jobs if j.department}
    regions = {name for name, pat in COUNTRY_HINTS if any(pat.search(x) for x in locs)}

    ev = [
        # Reach, measured honestly as hiring footprint — not brand recognition.
        _ev(D.BRAND_SIGNAL, scale(len(regions), 5),
            f"actively hiring across {len(regions)} world regions "
            f"({', '.join(sorted(regions)) or 'none detected'}); "
            "this is hiring footprint, NOT consumer brand recognition"),
        _ev(D.SYSTEM_SCALE, scale(len(jobs), 400),
            f"{len(jobs)} open postings on the official board"),
        _ev(D.CAREER_OPTIONALITY, scale(max(len(depts), len(regions) * 4), 25),
            f"{len(depts)} departments hiring across {len(regions)} regions"),
        _ev(D.TECHNICAL_DENSITY, tech / len(jobs),
            f"{tech}/{len(jobs)} postings are technical/data/product"),
        _ev(D.TALENT_NETWORK, scale(canada, 60),
            f"{canada} Canadian postings ({gta} in the GTA)"),
        # Weak, and recorded as weak.
        _ev(D.STABILITY, scale(len(jobs), 250),
            f"sustained hiring volume ({len(jobs)} live roles); operational "
            "signal only, not a financial assessment", SourceGrade.B),
    ]
    if students:
        ev.append(_ev(D.INTERNSHIP_PROGRAM,
                      min(1.0, 0.4 + 0.6 * scale(len(students_ca) * 4 + len(students), 25)),
                      f"{len(students)} student/co-op postings "
                      f"({len(students_ca)} in Canada)"))
    else:
        ev.append(_ev(D.INTERNSHIP_PROGRAM, 0.15,
                      "no student/co-op postings open in this hiring cycle"))

    ci = assess_company(ev)
    return {
        "employer": row["employer"], "connector": row["connector"],
        "jobs": len(jobs), "canada": canada, "gta": gta, "tech": tech,
        "students": len(students), "students_canada": len(students_ca),
        "regions": sorted(regions),
        "estimated_tier": ci.estimated_tier, "rated_tier": ci.rated_tier,
        "display_tier": ci.display_tier, "status": ci.rating_status,
        "known_score": ci.known_evidence_score,
        "conservative": ci.conservative_score, "coverage": ci.evidence_coverage,
    }


async def main() -> None:
    out = Path(sys.argv[1])
    rows = json.loads((out / "canada_discovery.json").read_text(encoding="utf-8"))
    sem = asyncio.Semaphore(6)

    async with HttpClient(max_retries=1, timeout=30) as http:
        async def g(r):
            async with sem:
                return await analyse(http, r)
        results = [r for r in await asyncio.gather(*[g(r) for r in rows]) if r]

    # Personal tier: for a Toronto co-op search, a company with no Canadian
    # hiring cannot be a top platform however large it is globally.
    for r in results:
        r["personal_tier"] = r["rated_tier"] or r["estimated_tier"]
        if r["canada"] == 0:
            r["personal_tier"] = "D"
            r["personal_note"] = "no Canadian postings — not actionable for you"
        elif r["students_canada"] > 0:
            r["personal_note"] = f"{r['students_canada']} Canadian student role(s) open"
        else:
            r["personal_note"] = "Canadian presence but no student roles this cycle"

    order = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
    results.sort(key=lambda r: (order.get(r["personal_tier"], 5),
                                -r["students_canada"], -r["canada"]))
    (out / "final_tiers.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    lines = ["COMPANY TIERS — personalised for a Toronto CS/DS co-op search",
             "=" * 100,
             "Evidence is measured from each employer's own board (grade A).",
             "Brand = hiring footprint across regions, NOT consumer recognition.",
             "Companies with zero Canadian postings are forced to D: not actionable.",
             ""]
    buckets: dict[str, list] = {}
    for r in results:
        buckets.setdefault(r["personal_tier"], []).append(r)
    for tier in ["S", "A", "B", "C", "D"]:
        rows_t = buckets.get(tier) or []
        if not rows_t:
            continue
        lines.append(f"\n{'=' * 100}\n{tier} TIER  ({len(rows_t)} companies)\n{'=' * 100}")
        lines.append(f"{'COMPANY':<24}{'FORMAL':<8}{'COV':>5}{'JOBS':>6}{'CA':>6}"
                     f"{'GTA':>5}{'STU-CA':>7}{'TECH%':>7}  NOTE")
        for r in rows_t:
            formal = r["rated_tier"] or f"{r['estimated_tier']}?"
            lines.append(
                f"{r['employer'][:23]:<24}{formal:<8}{r['coverage']*100:>4.0f}%"
                f"{r['jobs']:>6}{r['canada']:>6}{r['gta']:>5}{r['students_canada']:>7}"
                f"{r['tech']/max(r['jobs'],1)*100:>6.0f}%  {r['personal_note']}")
    (out / "final_tiers.txt").write_text("\n".join(lines), encoding="utf-8")

    print(f"tiered {len(results)} companies   max coverage "
          f"{max(r['coverage'] for r in results):.0%}")
    for tier in ["S", "A", "B", "C", "D"]:
        n = len(buckets.get(tier) or [])
        formal = sum(1 for r in (buckets.get(tier) or []) if r["rated_tier"])
        print(f"  {tier}: {n:3d}  (formally rated: {formal})")


if __name__ == "__main__":
    asyncio.run(main())
