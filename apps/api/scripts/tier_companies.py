"""First-pass company tiering from OFFICIAL board evidence only.

Every dimension below is measured from the employer's own ATS board, which is a
grade-A first-party source. Dimensions a job board cannot show — global brand
signal, financial stability — are left UNKNOWN, which lowers evidence coverage
and keeps most companies provisional. That is the honest outcome, not a bug:
a tier is never asserted from reputation.

Personalised to this candidate: Canada presence and student/co-op hiring are
what matter, so they drive the Canada-market and internship-program dimensions.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

from app.company.intelligence import CompanyDimension as D
from app.company.intelligence import Evidence, SourceGrade, assess_company
from app.connectors.http import HttpClient
from app.connectors.registry import get_connector
from app.schemas.connector import SourceConfig
from app.sources.boards import BOARDS

CANADA = re.compile(r"(toronto|canada|ontario|\bON\b|\bBC\b|\bAB\b|\bQC\b|vancouver|"
                    r"montr|ottawa|waterloo|calgary|mississauga)", re.I)
GTA = re.compile(r"(toronto|mississauga|brampton|markham|vaughan|scarborough|"
                 r"etobicoke|north york|richmond hill|oakville)", re.I)
STUDENT = re.compile(r"\b(intern|internship|co-?op|student|campus|new ?grad|"
                     r"early career|rotational)\b", re.I)
TECH = re.compile(r"(software|backend|front-?end|full ?stack|data|analytics|analyst|"
                  r"machine learning|\bml\b|\bai\b|platform|infrastructure|devops|"
                  r"cloud|engineer|developer|scientist|product)", re.I)


def _ev(dim, value, summary, url):
    """Board-derived evidence. The board IS the employer's own system => grade A."""
    return Evidence(url=url, source_type="official_ats", grade=SourceGrade.A,
                    supports_dimension=dim, summary=summary, value=value)


def _scale(n: int, full: int) -> float:
    return max(0.0, min(1.0, n / full))


async def analyse(http, board) -> dict | None:
    try:
        conn = get_connector(board.connector)
    except KeyError:
        return None
    cfg = SourceConfig(connector_key=board.connector, external_id=board.external_id,
                       display_name=board.employer, config=board.config or {})
    try:
        res = await conn.fetch(cfg, http)
    except Exception:
        return None
    jobs = res.raw_jobs
    if not jobs:
        return None

    locs = [(j.locations[0].raw_text if j.locations else "") or "" for j in jobs]
    canada = sum(1 for x in locs if CANADA.search(x))
    gta = sum(1 for x in locs if GTA.search(x))
    student = [j for j in jobs if STUDENT.search(j.title)]
    student_ca = [j for j in student
                  if CANADA.search((j.locations[0].raw_text if j.locations else "") or "")]
    tech = sum(1 for j in jobs if TECH.search(j.title))
    depts = {(j.department or "").strip().lower() for j in jobs if j.department}
    countries = {x.split(",")[-1].strip().lower() for x in locs if x}

    url = f"board:{board.connector}:{board.external_id}"
    evidence: list[Evidence] = [
        _ev(D.SYSTEM_SCALE, _scale(len(jobs), 400),
            f"{len(jobs)} open postings on the official board", url),
        _ev(D.CAREER_OPTIONALITY, _scale(max(len(depts), len(countries)), 25),
            f"{len(depts)} departments / {len(countries)} location groups hiring", url),
        _ev(D.TECHNICAL_DENSITY, tech / len(jobs),
            f"{tech}/{len(jobs)} postings are technical/data/product", url),
    ]
    # Internship programme: measured from actual student hiring, weighted to Canada.
    if student:
        evidence.append(_ev(
            D.INTERNSHIP_PROGRAM,
            min(1.0, 0.35 + 0.65 * _scale(len(student_ca) * 3 + len(student), 30)),
            f"{len(student)} student/co-op postings ({len(student_ca)} in Canada)", url))
    else:
        # Absence is itself evidence, and a weak one for an intern search.
        evidence.append(_ev(D.INTERNSHIP_PROGRAM, 0.12,
                            "no student/co-op postings currently open", url))
    # Canada presence feeds talent network (local pipeline for this candidate).
    evidence.append(_ev(D.TALENT_NETWORK, _scale(canada, 60),
                        f"{canada} Canadian postings ({gta} in the GTA)", url))
    # BRAND_SIGNAL and STABILITY are deliberately absent: a job board cannot
    # evidence them, so they stay unknown and drag coverage down honestly.

    ci = assess_company(evidence)
    return {
        "employer": board.employer, "connector": board.connector,
        "jobs": len(jobs), "canada": canada, "gta": gta,
        "student": len(student), "student_canada": len(student_ca), "tech": tech,
        "estimated_tier": ci.estimated_tier, "rated_tier": ci.rated_tier,
        "display_tier": ci.display_tier, "status": ci.rating_status,
        "score": ci.known_evidence_score, "conservative": ci.conservative_score,
        "coverage": ci.evidence_coverage,
    }


async def main() -> None:
    out = Path(sys.argv[1])
    sem = asyncio.Semaphore(6)
    async with HttpClient(max_retries=1, timeout=30) as http:
        async def guarded(b):
            async with sem:
                return await analyse(http, b)
        results = [r for r in await asyncio.gather(*[guarded(b) for b in BOARDS]) if r]

    results.sort(key=lambda r: (-r["conservative"], -r["canada"]))
    (out / "company_tiers.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    buckets: dict[str, list[dict]] = {}
    for r in results:
        key = r["rated_tier"] or f"{r['estimated_tier']}? (provisional)"
        buckets.setdefault(key, []).append(r)

    lines = ["COMPANY TIERS — derived from official board evidence only", "=" * 92,
             "Brand signal and stability are NOT measurable from a job board, so they",
             "stay unknown; that keeps coverage moderate and most tiers provisional.", ""]
    for key in sorted(buckets, key=lambda k: (len(k), k)):
        rows = buckets[key]
        lines.append(f"\n### {key}   ({len(rows)} companies)")
        lines.append(f"{'COMPANY':<22}{'JOBS':>6}{'CA':>5}{'GTA':>5}{'STUDENT':>9}"
                     f"{'TECH':>6}{'SCORE':>7}{'COV':>6}")
        for r in rows[:40]:
            lines.append(f"{r['employer'][:21]:<22}{r['jobs']:>6}{r['canada']:>5}"
                         f"{r['gta']:>5}{r['student']:>9}{r['tech']:>6}"
                         f"{r['conservative']:>7.0f}{r['coverage']*100:>5.0f}%")
    (out / "company_tiers.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"analysed {len(results)} companies")
    for key in sorted(buckets):
        print(f"  {key:<26} {len(buckets[key])}")


if __name__ == "__main__":
    asyncio.run(main())
