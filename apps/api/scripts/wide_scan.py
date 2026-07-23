"""Wide scan across many first-party ATS boards.

Local research tool, not part of the served app. Writes UTF-8 to a file because
the Windows console codec cannot render the postings.

Politeness: bounded concurrency, per-request timeout and retry come from
HttpClient. Only public job-board endpoints are touched.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

from app.connectors.ashby import AshbyConnector
from app.connectors.greenhouse import GreenhouseConnector
from app.connectors.http import HttpClient
from app.connectors.lever import LeverConnector
from app.schemas.connector import SourceConfig

GREENHOUSE = """stripe faire instacart databricks figma doordash affirm robinhood verkada
benchling plaid brex gusto airtable asana dropbox cloudflare datadog mongodb gitlab twilio
coinbase sofi rippling deel vanta retool sourcegraph supabase miro atlassian snowflake
confluent hashicorp sentry launchdarkly amplitude segment fivetran hex samsara scaleai
duolingo reddit pinterest lyft flexport nuro applied-intuition anduril discord grammarly
sigmacomputing clickhouse temporal chainalysis alloy ramp2 mercury modernhealth
shopify wealthsimple hootsuite clio 1password jobber wave koho borrowell dapperlabs
axonify d2l ecobee geotab kinaxis lightspeed nuvei opentext coveo benchsci xanadu
untether sanctuaryai deepgenomics bluedot introhive verafin thinkific properly""".split()

LEVER = """waabi benchsci ada kobo ritual drop neofinancial layer6 deeplite signal1
applydigital points mapsted tenstorrent cyclica phenomic vectorinstitute
netlify plaid attentive cresta scale pachyderm""".split()

ASHBY = """cohere openai notion linear vercel ramp anthropic tenstorrent coveo clio
perplexity mistral together elevenlabs harvey sierra decagon glean abridge cursor
replit modal baseten runway suno character deepgram assemblyai weightsandbiases
neon planetscale railway render clerk resend inngest trigger browserbase""".split()

# Word-boundary matching. "Internal" must never match "intern".
TERM = re.compile(
    r"\b(intern|interns|internship|co-?op|new ?grad|university ?grad|student|campus|"
    r"apprentice|summer 20\d\d|fall 20\d\d|winter 20\d\d)\b",
    re.I,
)
CANADA = re.compile(r"(toronto|canada|ontario|vancouver|montr|waterloo|ottawa|calgary)", re.I)
REMOTE = re.compile(r"\bremote\b", re.I)
# Roles the candidate actually targets (incl. his own #1: data/product analyst).
RELEVANT = re.compile(
    r"(software|backend|back-end|full ?stack|data|analytics|analyst|machine learning|"
    r"\bml\b|\bai\b|platform|infrastructure|product|research engineer|business intelligence|"
    r"\bbi\b|engineer|developer|scientist)",
    re.I,
)


async def scan_one(conn, key, token, http, out):
    try:
        res = await conn.fetch(
            SourceConfig(connector_key=key, external_id=token, display_name=token), http
        )
    except Exception:
        return None
    hits = [j for j in res.raw_jobs if TERM.search(j.title) and RELEVANT.search(j.title)]
    return (key, token, len(res.raw_jobs), hits)


async def main() -> None:
    out = Path(sys.argv[1]) / "wide_scan.txt"
    sem = asyncio.Semaphore(6)  # be polite

    async with HttpClient(max_retries=1) as http:
        async def guarded(conn, key, token):
            async with sem:
                return await scan_one(conn, key, token, http, out)

        tasks = []
        for key, conn, tokens in (
            ("greenhouse", GreenhouseConnector(), GREENHOUSE),
            ("lever", LeverConnector(), LEVER),
            ("ashby", AshbyConnector(), ASHBY),
        ):
            tasks += [guarded(conn, key, t) for t in tokens]

        results = [r for r in await asyncio.gather(*tasks) if r]

    lines: list[str] = []
    working = [r for r in results if r[2] > 0]
    lines.append(f"Boards reachable with postings: {len(working)} / {len(results)} attempted")
    lines.append("")

    ca_rows, remote_rows, other_rows = [], [], []
    for key, token, _total, hits in sorted(working, key=lambda r: -len(r[3])):
        for j in hits:
            loc = (j.locations[0].raw_text if j.locations else "") or ""
            row = (token, j.title.strip(), loc.strip(), j.canonical_application_url,
                   str(j.source_posted_at or "")[:10], key)
            if CANADA.search(loc):
                ca_rows.append(row)
            elif REMOTE.search(loc):
                remote_rows.append(row)
            else:
                other_rows.append(row)

    def dump(title, rows):
        lines.append("=" * 100)
        lines.append(f"{title}  ({len(rows)})")
        lines.append("=" * 100)
        for token, t, loc, url, posted, _k in sorted(rows, key=lambda r: (r[0], r[1])):
            lines.append(f"{token:16s} | {t[:62]:62s} | {loc[:26]:26s} | posted {posted}")
            lines.append(f"{'':16s} | {url}")
        lines.append("")

    dump("CANADA", ca_rows)
    dump("REMOTE", remote_rows)
    dump("OTHER (US/global — check work authorization)", other_rows)

    lines.append("Boards that returned nothing / failed:")
    dead = [f"{r[0]}:{r[1]}" for r in results if r[2] == 0]
    lines.append("  " + ", ".join(dead))

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    print(f"CANADA={len(ca_rows)} REMOTE={len(remote_rows)} OTHER={len(other_rows)}")


if __name__ == "__main__":
    asyncio.run(main())
