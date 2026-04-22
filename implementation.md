# PIF Workflow Extension — Implementation Plan

## Context

The PIF team has an existing automated system that generates weekly Confluence progress reports using Claude Code + Atlassian MCP tools. The goal is to extend this into a full **PM command center**: a single Confluence page with checkboxes that drives what the script does each run — board reports, ticket quality audits, sprint summaries, description fixes, and more.

**Persona:** The script is a Product Manager assistant. All output is PM-friendly (plain language, actionable, checklist-style where appropriate).

---

## Current System Summary

| Item | Value |
|---|---|
| Working dir | `/Users/zop1269/Desktop/workflow_setup_claude` |
| Jira cloud | `kroger.atlassian.net` |
| Jira project | `DCPFS` |
| Confluence space | `apiprogram` |
| Weekly page ID | `514261050` |
| Board | Dec-Titans (PIF) Scrum Board (ID 4896) |
| Epic fallback keys | DCPFS-27809, DCPFS-27807, DCPFS-27772, DCPFS-27778 |
| MCP tools | `searchJiraIssuesUsingJql`, `getConfluencePage`, `updateConfluencePage` |
| Prompt pattern | `claude --dangerously-skip-permissions -p <prompt.md>` |

---

## New File Structure

```
workflow_setup_claude/
│
├── run_command.sh                    ← NEW: main entry point (replaces/wraps run_weekly_update.sh)
├── run_weekly_update.sh              ← KEEP: backward compat (still works unchanged)
├── weekly_update_prompt.md           ← KEEP: backward compat
│
├── prompts/
│   ├── dispatcher.md                 ← NEW: reads command page, runs checked commands
│   ├── board_report.md               ← NEW: per-member activity from comments
│   ├── sprint_summary.md             ← NEW: sprint overview / metrics
│   ├── ticket_quality.md             ← NEW: audit tickets for missing desc/AC
│   ├── fix_descriptions.md           ← NEW: generate AI-drafted desc+AC for ticket keys
│   ├── browse_folder.md              ← NEW: list and summarize team Confluence folder
│   └── setup_command_page.md         ← NEW: one-time: create the command center page
│
├── scripts/                          ← KEEP: all existing Python scripts unchanged
├── output/                           ← KEEP + extend
│   ├── board_report_YYYY-MM-DD.json
│   ├── sprint_summary_YYYY-MM-DD.json
│   └── ticket_quality_YYYY-MM-DD.json
│
└── logs/                             ← KEEP: all runs log here
```

---

## Confluence Command Center Page

### Format (markdown that gets created by setup_command_page.md)

```markdown
# PIF Automation Commands

> Control panel for automated team workflows. Check boxes below then run `./run_command.sh` from terminal.
> **Last run:** _(auto-updated)_

---

## Commands

- [ ] **weekly_progress** — Weekly sprint progress update → posts to PIF Weekly Progress 2026
- [ ] **sprint_summary** — Current sprint metrics (ticket counts by status, member, epic)
- [ ] **board_report** — What each team member has done this week (from ticket comments)
- [ ] **ticket_quality** — Audit: which tickets are missing description or acceptance criteria
- [ ] **fix_descriptions** — Generate AI-drafted descriptions + AC for tickets listed below
- [ ] **browse_folder** — Browse team Confluence space and summarize page structure

---

## Configuration

**Ticket quality scope:** `sprint`  _(options: sprint | backlog | all)_
**Board report — days back:** `7`
**Fix descriptions — ticket keys:** _(paste keys here, comma-separated, e.g. DCPFS-12345, DCPFS-67890)_
**Create page — title:** _(page title if creating a page)_
**Create page — parent ID:** `514261050`

---

_Run: `./run_command.sh` — script executes all checked commands in order._
```

### Config Constants (used in all prompts)

```
COMMAND_PAGE_ID: <set after setup>    ← user fills this in run_command.sh after first setup
WEEKLY_PAGE_ID:  514261050
CLOUD_ID:        kroger.atlassian.net
PROJECT:         DCPFS
SPACE:           apiprogram
EPIC_KEYS:       DCPFS-27809, DCPFS-27807, DCPFS-27772, DCPFS-27778
AC_FIELD:        customfield_10016    ← configurable; acceptance criteria custom field
```

---

## File 1: `run_command.sh`

**Purpose:** Main entry point. Handles date computation, flag parsing, dispatching.

```bash
# Usage
./run_command.sh                        # read command page, run all checked items
./run_command.sh --command weekly       # run one specific command
./run_command.sh --command board-report
./run_command.sh --command sprint-summary
./run_command.sh --command ticket-quality
./run_command.sh --command fix-descriptions
./run_command.sh --command browse-folder
./run_command.sh --setup                # one-time: create command center page in Confluence
./run_command.sh --dry-run              # print what would run, don't execute
```

**Logic:**
1. Set PATH (same as run_weekly_update.sh — covers cron/launchd)
2. Compute `WEEK_START` (last Monday) and `WEEK_END` (today) — macOS date syntax
3. Also compute `TODAY` and `COMMAND_PAGE_ID` from env or hardcoded constant
4. If `--setup`: run `claude -p prompts/setup_command_page.md`
5. If `--command <name>`: substitute date vars into `prompts/<name>.md` and run claude
6. If no flags: substitute date vars into `prompts/dispatcher.md` and run claude
7. Log everything to `logs/command_YYYY-MM-DD_HH-MM-SS.log`
8. Same pseudo-TTY pattern as existing script (`script -q /dev/null`)

**Placeholders substituted into prompts:**
- `WEEK_START_PLACEHOLDER` → last Monday date
- `WEEK_END_PLACEHOLDER` → today
- `TODAY_PLACEHOLDER` → today

---

## File 2: `prompts/dispatcher.md`

**Purpose:** Reads the Confluence command page, parses which checkboxes are checked, runs each command's workflow inline.

### Steps:

**Step 1 — Read command page**
```
tool: getConfluencePage
cloudId: kroger.atlassian.net
pageId: COMMAND_PAGE_ID
contentFormat: markdown
```
Parse the result to find every line matching `- [x] **<command>**`. Collect the list of checked commands. Also parse the Configuration section for:
- `ticket_quality_scope`
- `board_report_days`
- `fix_descriptions_keys` (comma-separated ticket keys)
- `create_page_title`, `create_page_parent`

Print: `→ [Dispatcher] Commands to run: {list}`

If no commands checked → print "No commands checked on the command page. Nothing to do." and stop.

**Step 2 — Run each checked command inline (in order)**

For each checked command name, execute the corresponding workflow (embedded below in the prompt). Print a separator:
```
═══════════════════════════════════
▶ Running: {command_name}
═══════════════════════════════════
```

**Step 3 — Update command page**
After all commands complete:
- Uncheck all `[x]` checkboxes back to `[ ]`
- Update the "Last run:" line to current timestamp
- Call `updateConfluencePage` with the modified body

Print: `✅ All done. Command page reset.`

---

## File 3: `prompts/board_report.md`

**Purpose:** Generate a per-member activity report by reading ticket comments. Posts to a new Confluence page.

### Steps:

**Step 1 — Get active sprint**
```
JQL: project = DCPFS AND sprint in openSprints()
fields: ["customfield_10020"]
maxResults: 1
```
Extract sprint name (e.g. DCP 2026Q1.6).

**Step 2 — Fetch all PIF sprint tickets with full comments**
```
JQL: project = DCPFS AND sprint in openSprints() AND "Epic Link" in (DCPFS-27809, DCPFS-27807, DCPFS-27772, DCPFS-27778)
fields: ["summary", "status", "assignee", "comment", "parent", "issuetype"]
maxResults: 100
responseContentFormat: markdown
```
For each ticket, extract:
- `key`, `summary`, `status.name`, `assignee.displayName`
- ALL comments: `comment.comments[]` → for each: `author.displayName`, `created`, `body` (first 400 chars)

Skip tickets where `issuetype.name` is Epic or Objective.

**Step 3 — Group by assignee**
Build a map: `{ "Member Name": [ {ticket, status, comments_by_this_member[]}, ... ] }`

For "comments by this member": include ALL comments in the ticket, noting the author — this shows the full conversation context per ticket the member owns.

**Step 4 — Synthesize per-member summaries**
For each member:
- **Completed this week**: tickets where status = Done/Closed/Deployed + recent comment evidence
- **In Progress**: active tickets with what they're working on (from comments)
- **Key contributions**: notable comments showing decisions, reviews, unblocking
- **Ticket count**: total owned / completed / in-progress

Write `output/board_report_TODAY_PLACEHOLDER.json`:
```json
{
  "sprint": "DCP 2026Q1.6",
  "week": "WEEK_START_PLACEHOLDER to WEEK_END_PLACEHOLDER",
  "members": [
    {
      "name": "Jaiswal, Divyanshu",
      "completed": [],
      "in_progress": [],
      "summary": "2-3 sentence plain English summary"
    }
  ]
}
```

**Step 5 — Build Confluence page**
Title: `PIF Board Report — WEEK_START_PLACEHOLDER to WEEK_END_PLACEHOLDER`
Parent: `514261050` (or from config)

Format:
```markdown
# PIF Board Report
## {Sprint Name} | {Week Range}

---

### {Member Name}
**Summary:** {2-3 sentence plain English summary of their week}

| Ticket | Summary | Status | Key Activity |
|---|---|---|---|
| DCPFS-XXXXX | ... | In Progress | Comment excerpt showing what they did |

---
```

**Step 6 — Create or update Confluence page**
```
tool: createConfluencePage (if new) or updateConfluencePage (if exists)
cloudId: kroger.atlassian.net
space: apiprogram
parentId: 514261050
title: "PIF Board Report — {week range}"
body: {built above}
contentFormat: markdown
```

Print: `✅ Board report posted: {url}`

---

## File 4: `prompts/ticket_quality.md`

**Purpose:** Audit all sprint/backlog tickets for missing description and acceptance criteria. Post a PM-friendly checklist to Confluence.

### Steps:

**Step 1 — Determine scope from config**
Scope options: `sprint` (default), `backlog`, `all`

Build JQL accordingly:
- `sprint`: `project = DCPFS AND sprint in openSprints() AND "Epic Link" in (...)`
- `backlog`: `project = DCPFS AND sprint not in openSprints() AND status = "To Do" AND "Epic Link" in (...)`
- `all`: `project = DCPFS AND status not in (Done, Closed) AND "Epic Link" in (...)`

**Step 2 — Fetch tickets with description + AC field**
```
fields: ["summary", "description", "status", "assignee", "parent", "issuetype", "customfield_10016"]
maxResults: 100
```
`customfield_10016` is the acceptance criteria field (configurable).

**Step 3 — Evaluate each ticket**
For each ticket (skip Epics/Objectives):

| Check | Pass condition |
|---|---|
| Has description | Field non-null and length > 50 chars |
| Description is meaningful | Not just a copy of the summary |
| Has AC | `customfield_10016` (or configured AC field) is non-null and non-empty |

Classify each ticket as:
- ✅ **Complete** — has both description and AC
- ⚠️ **Missing AC** — has description, no AC
- ⚠️ **Missing Description** — has AC or nothing, no description
- ❌ **Missing Both** — empty description AND no AC

**Step 4 — Generate AI draft suggestions**
For tickets classified as ⚠️ or ❌, generate:
- **Suggested description** (2-4 sentences based on summary + epic context)
- **Suggested AC** (3-5 bullet points)

Write `output/ticket_quality_TODAY_PLACEHOLDER.json`.

**Step 5 — Post PM-friendly Confluence page**
Title: `PIF Ticket Quality Report — TODAY_PLACEHOLDER`
Parent: `514261050`

---

## File 5: `prompts/fix_descriptions.md`

**Purpose:** Given specific ticket keys from the command page config, fetch each ticket and generate polished description + AC drafts. Post to a Confluence "draft" page for the PM to review and copy-paste into Jira.

### Steps:

**Step 1 — Read ticket keys from config**
Parse keys from command page config: `Fix descriptions — ticket keys: DCPFS-XXXXX, DCPFS-YYYYY`

If no keys → print message and skip.

**Step 2 — Fetch each ticket in detail**
```
fields: ["summary", "description", "status", "assignee", "parent", "comment", "customfield_10016", "labels", "priority"]
```

**Step 3 — Generate drafts for each ticket**
- Description draft (PM-style, 3-5 sentences): what, who benefits, expected outcome, technical context from comments
- AC draft (3-6 bullets, testable): Given/When/Then or "The system should..." phrasing

**Step 4 — Post Confluence draft page**
Title: `Description Drafts — TODAY_PLACEHOLDER`
Parent: from config

---

## File 6: `prompts/sprint_summary.md`

**Purpose:** Concise current-sprint overview with metrics and highlights.

### Steps:

1. Get sprint name via JQL
2. Fetch all PIF sprint tickets
3. Compute metrics: total, by status, by epic, by assignee, blocked list, done list
4. Create Confluence page: `PIF Sprint Summary — {sprint name} — TODAY_PLACEHOLDER`

---

## File 7: `prompts/browse_folder.md`

**Purpose:** Browse a Confluence space or parent page's children and summarize the content structure.

### Steps:

1. List pages under parent (apiprogram space / configured parent)
2. Fetch top 10 recent pages (title + first 200 chars)
3. Print tree-style summary to terminal; optionally create summary page

---

## File 8: `prompts/setup_command_page.md`

**Purpose:** One-time setup — creates the command center page in Confluence.

### Steps:
1. Print confirmation of parent page ID
2. Create page using `createConfluencePage` with the full command center markdown template
3. Print the new page ID and URL
4. Instruct user to add page ID to `run_command.sh` as `COMMAND_PAGE_ID`

---

## Backward Compatibility

- `run_weekly_update.sh` is **not modified** — still works exactly as before
- `weekly_update_prompt.md` is **not modified**
- All existing output files remain
- New `run_command.sh` is a separate script; nothing breaks

---

## Implementation Order

1. `run_command.sh` — shell orchestrator with all flags
2. `prompts/setup_command_page.md` — creates the command center page (needed first to get page ID)
3. `prompts/dispatcher.md` — reads command page, routes to inline workflows
4. `prompts/board_report.md`
5. `prompts/ticket_quality.md`
6. `prompts/fix_descriptions.md`
7. `prompts/sprint_summary.md`
8. `prompts/browse_folder.md`

---

## First-Run Checklist (for user)

```bash
# 1. Make executable
chmod +x run_command.sh

# 2. Create the command center page in Confluence
./run_command.sh --setup
# → note the page ID printed

# 3. Edit run_command.sh and set COMMAND_PAGE_ID to the printed value

# 4. Check that AC custom field is correct (default: customfield_10016)
#    Edit prompts/ticket_quality.md and prompts/fix_descriptions.md if different

# 5. Test a single command
./run_command.sh --command sprint-summary --dry-run
./run_command.sh --command sprint-summary

# 6. Use the command page
#    → Go to Confluence, open "PIF Automation Commands"
#    → Check the boxes you want
#    → Run: ./run_command.sh
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| All commands in single dispatcher prompt | One Claude invocation per run; cheaper, faster, simpler |
| Command page as control plane | PM can queue work without touching terminal |
| Report-only mode for ticket quality | Safe default; PM reviews before any Jira changes |
| AC as configurable field name | Different Jira instances use different custom field IDs |
| Prompts are self-contained | Each can also be run standalone with `--command` flag |
| Backward compat preserved | Existing weekly automation is not disrupted |
