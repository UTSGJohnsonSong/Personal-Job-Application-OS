# Job OS MCP Server

Gives an AI agent **memory** of your job search. Pair it with a browser MCP
(Chrome DevTools MCP / Playwright MCP) which provides the **hands**.

```
one agent session
├── job-os MCP   ← memory: queue, personal context, ammo library, write-back
└── browser MCP  ← hands: open the page, fill fields, upload the resume
                   (never clicks Submit)
```

## Install

```bash
pip install "mcp[cli]" httpx
```

## Configure

Add to your MCP client config (e.g. Claude Desktop `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "job-os": {
      "command": "python",
      "args": ["D:/A. Workspace/PersonalJobApplicationOS/apps/mcp/server.py"],
      "env": {
        "JOB_OS_API": "https://job-os-api-jstp.onrender.com",
        "JOB_OS_TOKEN": "<your API_TOKEN>"
      }
    }
  }
}
```

## Tools exposed

| Tool | Purpose |
|---|---|
| `get_apply_queue` | ranked apply queue — call this at 投递时间 |
| `add_to_queue` / `remove_from_queue` | manage the queue |
| `list_jobs` / `get_job` | browse discovered jobs |
| `get_ammo` / `add_ammo` / `mark_ammo_used` | the 弹药库 |
| `record_application` | write back every Q&A + resume version used |
| `get_application_record` / `list_application_records` | read records |
| `set_application_status` | update status (cannot set `submitted`) |
| `get_dashboard` | metrics + funnel |

## Deliberately NOT exposed

There is **no tool that submits an application**. Reaching `submitted` requires
the per-job human confirmation flow in the web app. `set_application_status`
rejects `submitted` at the API level.
