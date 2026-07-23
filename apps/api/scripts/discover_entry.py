"""Discover real recruiting entry points, starting from the official site.

No domain guessing. For each institution we start at its official page, follow
redirects, then look at what the page actually references: ATS vendor hosts,
embedded JSON endpoints, and JSON-LD. The point is to identify the vendor and
capture a usable config, or report honestly that we could not.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

from app.connectors.http import HttpClient

# Institution -> official pages to start from (their real websites).
STARTS: list[tuple[str, list[str]]] = [
    ("City of Toronto", ["https://www.toronto.ca/city-government/jobs/",
                         "https://jobs.toronto.ca/jobsatcity/"]),
    ("TTC", ["https://www.ttc.ca/about-the-ttc/careers"]),
    ("Metrolinx", ["https://www.metrolinx.com/en/about-us/careers"]),
    ("Ontario Public Service", ["https://www.gojobs.gov.on.ca/"]),
    ("GC Jobs", ["https://www.canada.ca/en/services/jobs/opportunities/government.html"]),
    ("Canada Job Bank", ["https://www.jobbank.gc.ca/"]),
    ("UHN", ["https://www.uhn.ca/corporate/Careers"]),
    ("SickKids", ["https://www.sickkids.ca/en/careers/"]),
    ("Vector Institute", ["https://vectorinstitute.ai/careers/"]),
    ("MaRS", ["https://www.marsdd.com/about/careers/"]),
    ("Communitech", ["https://www.communitech.ca/careers/"]),
    ("TechTO", ["https://www.techto.org/"]),
    ("DMZ", ["https://dmz.torontomu.ca/"]),
    ("Shopify", ["https://www.shopify.com/careers"]),
    ("Wealthsimple", ["https://www.wealthsimple.com/en-ca/careers"]),
    ("RBC", ["https://jobs.rbc.com/"]),
    ("Scotiabank", ["https://www.scotiabank.com/careers/en/careers.html"]),
]

VENDOR_HINTS = [
    (r"myworkdayjobs\.com/([\w-]+)/?", "workday"),
    (r"boards\.greenhouse\.io/([\w-]+)", "greenhouse"),
    (r"job-boards\.greenhouse\.io/([\w-]+)", "greenhouse"),
    (r"jobs\.lever\.co/([\w-]+)", "lever"),
    (r"jobs\.ashbyhq\.com/([\w-]+)", "ashby"),
    (r"jobs\.smartrecruiters\.com/([\w-]+)", "smartrecruiters"),
    (r"careers\.smartrecruiters\.com/([\w-]+)", "smartrecruiters"),
    (r"([\w-]+)\.icims\.com", "icims"),
    (r"([\w-]+)\.taleo\.net", "taleo"),
    (r"([\w-]+)\.oraclecloud\.com", "oracle_orc"),
    (r"(?:career|jobs)[\w.-]*\.(?:successfactors|sapsf)\.com", "successfactors"),
    (r"([\w-]+)\.wd(\d)\.myworkdayjobs\.com", "workday"),
    (r"([\w-]+)\.bamboohr\.com", "bamboohr"),
    (r"([\w-]+)\.workable\.com", "workable"),
    (r"phenompeople|phenom\.com", "phenom"),
    (r"eightfold\.ai", "eightfold"),
    (r"avature\.net", "avature"),
]

# Endpoint shapes worth capturing when they appear in the page source.
ENDPOINT_HINTS = re.compile(
    r"""(?:"|')(/?(?:api|graphql|search|services)[^"'\s]{4,120})(?:"|')""", re.I
)


async def inspect(http, name: str, url: str) -> dict:
    out: dict = {"institution": name, "start": url}
    try:
        status, html, headers = await http.get_text(url)
    except Exception as exc:
        out["error"] = str(exc)[:120]
        return out

    out["status"] = status
    out["bytes"] = len(html or "")

    vendors: dict[str, set[str]] = {}
    for pattern, vendor in VENDOR_HINTS:
        for m in re.finditer(pattern, html or "", re.I):
            tok = m.group(1) if m.groups() else ""
            vendors.setdefault(vendor, set()).add(tok)
    out["vendors"] = {k: sorted(v)[:4] for k, v in vendors.items()}

    # Career links that leave the marketing site.
    links = set()
    for m in re.finditer(r'href=["\']([^"\']+)["\']', html or "", re.I):
        href = m.group(1)
        if re.search(r"(career|job|emplo|recruit)", href, re.I):
            links.add(urljoin(url, href))
    external = sorted({
        u for u in links
        if urlparse(u).netloc and urlparse(u).netloc != urlparse(url).netloc
    })
    out["external_career_links"] = external[:8]

    endpoints = sorted(set(ENDPOINT_HINTS.findall(html or "")))
    out["candidate_endpoints"] = [e for e in endpoints
                                  if re.search(r"(job|search|posting|requisition|career)", e, re.I)][:8]

    ld = re.findall(r'application/ld\+json[^>]*>(.*?)</script>', html or "", re.S)
    out["jsonld_blocks"] = len(ld)
    out["jsonld_has_jobposting"] = any("JobPosting" in b for b in ld)
    return out


async def main() -> None:
    outdir = Path(sys.argv[1])
    results = []
    sem = asyncio.Semaphore(5)

    async with HttpClient(max_retries=1, timeout=25) as http:
        async def guarded(name, url):
            async with sem:
                return await inspect(http, name, url)

        tasks = [guarded(name, u) for name, urls in STARTS for u in urls]
        results = await asyncio.gather(*tasks)

    (outdir / "entry_discovery.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")

    for r in results:
        name = r["institution"]
        if r.get("error"):
            print(f"  {name:24s} ERROR {r['error'][:50]}")
            continue
        vend = ", ".join(f"{k}={v}" for k, v in (r.get("vendors") or {}).items())
        ld = "JSON-LD:JobPosting" if r.get("jsonld_has_jobposting") else ""
        print(f"  {name:24s} {r['status']} {r['bytes'] // 1024:4d}KB  "
              f"{vend[:70] or '(no vendor found)':<70} {ld}")
        for link in (r.get("external_career_links") or [])[:3]:
            print(f"        -> {link[:100]}")


if __name__ == "__main__":
    asyncio.run(main())
