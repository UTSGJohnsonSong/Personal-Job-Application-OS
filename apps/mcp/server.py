"""Job OS MCP server — gives an AI agent memory of the job search.

Pairs with a browser MCP (Chrome DevTools / Playwright MCP) which provides the
"hands". This server provides the "memory": the apply queue, the user's
confirmed personal context, the ammo library, and write-back of what actually
happened.

Deliberately NOT exposed as a tool: anything that submits an application. The
submit path requires the per-job human confirmation flow in the web app.

Run:
    JOB_OS_API=https://job-os-api-jstp.onrender.com \
    JOB_OS_TOKEN=... \
    python apps/mcp/server.py
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

API = os.environ.get("JOB_OS_API", "http://localhost:8000").rstrip("/")
TOKEN = os.environ.get("JOB_OS_TOKEN", "")

mcp = FastMCP("job-os")


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


async def _req(method: str, path: str, **kw) -> Any:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.request(method, f"{API}{path}", headers=_headers(), **kw)
        if resp.status_code >= 400:
            return {"error": resp.status_code, "detail": resp.text[:500]}
        return resp.json()


# ----------------------------------------------------------------- queue

@mcp.tool()
async def get_apply_queue() -> Any:
    """Get the user's apply queue ("想投列表"), already ranked.

    Call this at the start of an application session. Highest-value job first.
    Check `warnings` — a queued job whose source closed should not be applied to.
    """
    return await _req("GET", "/queue")


@mcp.tool()
async def add_to_queue(job_id: str, note: str | None = None) -> Any:
    """Add a job to the apply queue."""
    return await _req("POST", f"/queue/{job_id}", json={"note": note})


@mcp.tool()
async def remove_from_queue(job_id: str) -> Any:
    """Remove a job from the apply queue."""
    return await _req("DELETE", f"/queue/{job_id}")


# ----------------------------------------------------------------- jobs

@mcp.tool()
async def list_jobs(category: str | None = None, limit: int = 50) -> Any:
    """Browse discovered jobs. Categories: new, strong_match, manual_review, etc."""
    q = f"?limit={limit}" + (f"&category={category}" if category else "")
    return await _req("GET", f"/jobs{q}")


@mcp.tool()
async def get_job(job_id: str) -> Any:
    """Full job detail including description and match breakdown."""
    return await _req("GET", f"/jobs/{job_id}")


# ----------------------------------------------------------------- ammo

@mcp.tool()
async def get_ammo(
    category: str | None = None, direction: str | None = None, q: str | None = None
) -> Any:
    """Browse the ammo library (弹药库): resume bullets, projects, stories,
    answer templates, cover paragraphs — 母本 with their 变体.

    Use this to assemble tailored material instead of inventing content.
    Only use blocks as-is or recombined; never fabricate new claims.
    """
    parts = []
    if category:
        parts.append(f"category={category}")
    if direction:
        parts.append(f"direction={direction}")
    if q:
        parts.append(f"q={q}")
    return await _req("GET", "/ammo" + ("?" + "&".join(parts) if parts else ""))


@mcp.tool()
async def add_ammo(
    category: str,
    title: str,
    content: str,
    tags: list[str] | None = None,
    direction: str | None = None,
    variant_of: str | None = None,
) -> Any:
    """Add a block to the ammo library. Categories: resume_bullet, project,
    skill_combo, story, answer_template, cover_paragraph, headline, other."""
    return await _req(
        "POST",
        "/ammo",
        json={
            "category": category, "title": title, "content": content,
            "tags": tags or [], "direction": direction, "variant_of": variant_of,
            "source": "generated_draft",
        },
    )


@mcp.tool()
async def mark_ammo_used(block_id: str) -> Any:
    """Record that an ammo block was actually used in an application."""
    return await _req("POST", f"/ammo/{block_id}/used")


# ----------------------------------------------------------------- records

@mcp.tool()
async def record_application(
    application_id: str,
    answers: list[dict],
    resume_version_name: str | None = None,
    cover_letter: str | None = None,
    documents: list[str] | None = None,
    risks: list[str] | None = None,
    uncertainties: list[str] | None = None,
) -> Any:
    """Write back exactly what was used for this application.

    `answers` is a list of {question, answer, field_type?, is_sensitive?,
    needs_user_input?, answer_source?}. Record EVERY question on the form,
    including ones left blank for the user — mark those needs_user_input=true.

    This is what makes the record expandable on the site later.
    """
    return await _req(
        "PUT",
        f"/records/{application_id}",
        json={
            "answers": answers,
            "resume_version_name": resume_version_name,
            "cover_letter": cover_letter,
            "documents": documents or [],
            "risks": risks or [],
            "uncertainties": uncertainties or [],
        },
    )


@mcp.tool()
async def get_application_record(application_id: str) -> Any:
    """Read the full record: status, resume version used, every Q&A, timeline."""
    return await _req("GET", f"/records/{application_id}")


@mcp.tool()
async def list_application_records(status: str | None = None) -> Any:
    """List all application records, optionally filtered by status."""
    return await _req("GET", "/records" + (f"?status={status}" if status else ""))


@mcp.tool()
async def set_application_status(
    application_id: str, status: str, note: str | None = None
) -> Any:
    """Update an application's status (e.g. application_started, rejected,
    interview). Cannot set `submitted` — that requires the user's per-job
    confirmation in the web app.
    """
    return await _req(
        "POST", f"/records/{application_id}/status",
        json={"status": status, "note": note},
    )


@mcp.tool()
async def get_dashboard() -> Any:
    """Overview metrics and funnel — useful for weekly review."""
    return await _req("GET", "/dashboard/overview")


if __name__ == "__main__":
    mcp.run()
