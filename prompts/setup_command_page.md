# PIF Setup — Create Command Center Page

You are running an automated setup workflow. Follow every step below in order. Do not stop for clarification.

## Configuration

- **cloudId**: `CLOUD_ID_PLACEHOLDER`
- **spaceId**: `SPACE_ID_PLACEHOLDER`
- **parentId**: `COMMAND_PAGE_PARENT_ID_PLACEHOLDER`

---

## Step 1 — Create the command center page

Call `createConfluencePage` with:

```
cloudId: CLOUD_ID_PLACEHOLDER
spaceId: SPACE_ID_PLACEHOLDER
parentId: COMMAND_PAGE_PARENT_ID_PLACEHOLDER
title: PIF Automation Commands
contentFormat: markdown
status: current
body: (the full markdown below, exactly as written)
```

**Page body to create:**

```markdown
# PIF Automation Commands

> Control panel for automated team workflows. Check boxes below, then run `./run_command.sh` from terminal.
> **Last run:** _(not yet run)_

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
**Create page — parent ID:** `COMMAND_PAGE_PARENT_ID_PLACEHOLDER`

---

_Run: `./run_command.sh` — script reads this page and executes all checked commands in order._
_To run one command directly: `./run_command.sh --command sprint_summary`_
```

---

## Step 2 — Print result

After the page is created, print:

```
✅ Command center page created successfully.

Page ID:  {id from API response}
URL:      https://kroger.atlassian.net/wiki/spaces/apiprogram/pages/{id}

Next step: open config.sh and set COMMAND_PAGE_ID="{id}"
Then run: ./run_command.sh --dry-run   (to verify config)
```

If creation fails, print the error and stop.
