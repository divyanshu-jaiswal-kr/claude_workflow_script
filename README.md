# PIF Weekly Confluence Update — Automated Workflow

Automatically generates weekly sprint progress updates for the PIF team and publishes them to the [PIF Weekly Progress 2026](https://kroger.atlassian.net/wiki/spaces/apiprogram/pages/514261050/PIF+Weekly+Progress+2026) Confluence page every Friday at 18:00.

---

## Overview

Each Friday, the workflow:
1. Fetches the active sprint and this week's updated PIF tickets from Jira
2. Reads the current Confluence page and parses the most recent week's table (to avoid repeating content)
3. Runs Claude Code to synthesize per-epic progress summaries
4. Prepends a new formatted table section to the Confluence page

The output table looks like:

```
### DCP 2026Q1.6
### 13th April 2026 - 19th April 2026

| Service | Progress | Next Steps | Blocker/ Targets |   |
| --- | --- | --- | --- | --- |
| Catalog V2_Q1 Iterative tech enhancements | ... | ... | ... |   |
| Working PoC for Catalog bulk data delivery | ... | ... | ... |   |
```

---

## Architecture

All Jira and Confluence API calls go through **MCP tools** (authenticated automatically via Claude's Atlassian plugin — no credentials needed in environment variables). Python scripts in `scripts/` are available as standalone utilities for local file processing only.

```
run_weekly_update.sh
│
└── claude --dangerously-skip-permissions -p weekly_update_prompt.md
      │
      ├── Step 1: MCP searchJiraIssuesUsingJql → active sprint name
      │           Writes: output/sprint_info.json
      │
      ├── Step 2: MCP searchJiraIssuesUsingJql → discover PIF epics (text search + fallback)
      │
      ├── Step 3: MCP searchJiraIssuesUsingJql → tickets updated this week
      │           Writes: output/tickets_by_epic.json
      │
      ├── Step 4: MCP getConfluencePage → full page body + parse last week's table
      │           Writes: output/last_week.json
      │
      ├── Step 5: Synthesize per-epic Progress / Next Steps / Blockers
      │           (skips anything already in last_week.json)
      │           Writes: output/new_section.json
      │
      ├── Step 6-7: Build updated page body (new section prepended)
      │
      └── Step 8: MCP updateConfluencePage → publish
```

### Python scripts (standalone utilities)

The files in `scripts/` implement the same logic using direct REST API calls and env var credentials. They are **not called in the automated workflow** — MCP handles all API operations. Use them for:
- Manual testing with explicit credentials
- Debugging individual pipeline stages
- Environments where MCP is not available

---

## Prerequisites

- **Claude Code CLI** (`claude` on your PATH) with the **Atlassian MCP plugin** configured — this provides authenticated Jira/Confluence access without needing API tokens
- **Python 3.10+** (only needed if using the standalone scripts in `scripts/`)
- macOS (date calculation uses macOS `date -v` syntax; adjust for Linux if needed)

---

## Setup

### 1. Make scripts executable

```bash
chmod +x run_weekly_update.sh setup_cron.sh
```

### 2. Test manually

```bash
# Dry run — logs dates and resolved prompt to logs/, does not execute Claude or touch Confluence
./run_weekly_update.sh --dry-run

# Full run (MCP handles all Jira + Confluence API calls)
./run_weekly_update.sh
```

### 3. Install the scheduler (macOS — recommended)

Use **launchd** (`setup_launchd.sh`) — it is the native macOS scheduler and is more reliable than cron. It:
- Runs as your user with the correct `HOME` and `PATH`
- Persists across reboots
- Requires no terminal or manual start after installation

```bash
./setup_launchd.sh
```

This installs a LaunchAgent that fires every Friday at 18:00.

```bash
# Verify it's loaded
launchctl list | grep com.pif.weekly-confluence-update

# Run it right now (without waiting for Friday)
launchctl start com.pif.weekly-confluence-update

# Remove it
./setup_launchd.sh --unload
```

### 3b. Alternative: cron (Linux / non-macOS)

```bash
./setup_cron.sh          # install
./setup_cron.sh --remove # remove
crontab -l               # verify
```

---

## File Structure

```
workflow_setup_claude/
├── README.md                    ← this file
├── run_weekly_update.sh         ← main orchestrator script
├── setup_launchd.sh             ← macOS LaunchAgent installer (recommended)
├── setup_cron.sh                ← cron installer (Linux / alternative)
├── weekly_update_prompt.md      ← Claude synthesis instructions
├── requirements.txt             ← Python dependencies
├── .env.example                 ← credential template
├── .env                         ← your credentials (gitignored)
├── .gitignore
│
├── scripts/
│   ├── fetch_jira.py            ← Step 1: Jira data fetch
│   ├── fetch_confluence.py      ← Step 2: Confluence page fetch + parse
│   └── update_confluence.py     ← Step 4: Confluence page update
│
├── output/                      ← intermediate files (gitignored, regenerated each run)
│   ├── sprint_info.json         ← sprint name + formatted week dates
│   ├── tickets_by_epic.json     ← tickets grouped by parent epic
│   ├── last_week.json           ← parsed rows from previous week's Confluence table
│   └── new_section.json         ← synthesized section ready to publish
│
└── logs/                        ← run logs (gitignored)
    └── weekly_update_YYYY-MM-DD_HH-MM-SS.log
```

---

## How It Works

### Sprint and Week Date Detection

`run_weekly_update.sh` computes the week range in bash before Claude runs. `date +%u` returns the day of week (1=Mon, 7=Sun). `WEEK_START` is set to last Monday using `date -v -${DAYS_SINCE_MON}d`. Both dates are substituted into `weekly_update_prompt.md` via `sed` before passing to Claude.

Claude fetches the active sprint by querying `project = DCPFS AND sprint in openSprints()` and reading `customfield_10020` — the sprint array field. The entry with `state = "active"` provides the quarter label (e.g., `DCP 2026Q1.6`).

### PIF Epic Discovery

Board 4896 (Dec-Titans PIF Scrum Board) is a *filtered view*, not a sprint board — it shares sprints with board 2182. Epic filtering is done via `"Epic Link" in (...)` in JQL.

Two strategies are combined:
1. **Text search:** JQL `summary ~ "APIPIF" OR summary ~ "Catalog V2" OR ...` — catches dynamically created/renamed epics
2. **Hardcoded fallback:** The fallback list in `weekly_update_prompt.md` always includes known epic keys. This is necessary because Jira full-text search silently misses epics whose names contain underscores (e.g., "Catalog V2_Q1 Iterative tech enhancements").

**Update the fallback list at the start of each quarter** when epics are renamed or replaced.

### Ticket Filtering

JQL: `project = DCPFS AND sprint in openSprints() AND status != "To Do" AND updated >= "{WEEK_START}" AND "Epic Link" in ({epic keys})`. If zero tickets match (nothing updated this week), Claude falls back to the full sprint without the date filter.

### No-Repeat Logic

After fetching the Confluence page, Claude parses the first table in the page body — this is always the most recently prepended week's entry. It extracts Service / Progress / Next Steps / Blockers into `output/last_week.json`. The synthesis step then compares each new cell against the matching last-week row and omits anything already reported — only delta content (new completions, status changes, new blockers) appears.

### Confluence Update Format

The MCP `updateConfluencePage` tool accepts markdown. New content is prepended to the full existing page body. The zero-width non-joiner character (`\u200c`) after each table block matches the spacing convention in the existing page.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `No open sprint found` | Sprint closed between runs | Check Jira board; verify `openSprints()` returns results |
| `0 tickets updated since {date}` | No activity this week | Claude auto-falls back to full sprint data |
| Epic missing from output | Jira text search missed underscore name | Add key to the fallback list in `weekly_update_prompt.md` Step 2 |
| Confluence page not updated | Claude timed out or MCP call failed | Check `logs/` for the run; re-run `./run_weekly_update.sh` manually |
| MCP auth error | Atlassian MCP plugin not configured | Ensure `claude` has the Atlassian plugin active; test with `claude` interactively |

### Run manually (full workflow)

```bash
cd workflow_setup_claude

# Dry run — logs to logs/, does not execute Claude
./run_weekly_update.sh --dry-run

# Full run
./run_weekly_update.sh
```

### Check output files after a run

```bash
cat output/sprint_info.json
python3 -m json.tool output/tickets_by_epic.json | head -60
cat output/last_week.json
cat output/new_section.json
```

### Rerun only the Claude synthesis step

```bash
cd workflow_setup_claude
# Assumes output/sprint_info.json, tickets_by_epic.json, last_week.json already exist
claude --dangerously-skip-permissions -p "$(cat weekly_update_prompt.md)"
```

---

## Updating Epic Keys Each Quarter

At the start of each new quarter, PIF epics are renamed or replaced. Update the hardcoded fallback list in [weekly_update_prompt.md](weekly_update_prompt.md) under **Step 2**:

```
**Important fallback:** Always include the following known PIF epic keys:
- `DCPFS-XXXXX` — New Epic Name Q2 2026
- ...
```

Also update the same list in [scripts/fetch_jira.py](scripts/fetch_jira.py) (`PIF_EPIC_KEYS_FALLBACK`) if you use those standalone scripts.

To find current PIF epic keys, search Jira directly:
```
JQL: project = DCPFS AND issuetype = Epic AND status not in (Closed, Done) AND (summary ~ "APIPIF" OR summary ~ "Catalog")
```

Or after a run, read the epic keys from output:
```bash
python3 -c "import json; d=json.load(open('output/tickets_by_epic.json')); [print(v['epic_key'], k) for k,v in d.items()]"
```

```bash

To activate full automation — one command, one time:

chmod +x setup_launchd.sh && ./setup_launchd.sh
After that: nothing. It runs every Friday at 18:00, logs to logs/, and publishes to Confluence automatically.
```