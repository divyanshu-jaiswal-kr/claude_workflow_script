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

| Command | What it does | Claude tokens |
|---|---|---|
| **weekly_progress** | Weekly sprint progress update → posts to PIF Weekly Progress 2026 | ~5k |
| **sprint_summary** | Current sprint metrics: ticket counts by status, member, and epic | 0 |
| **board_report** | What each team member did this week, based on ticket comments | ~1k |
| **ticket_quality** | Audit which tickets are missing description or acceptance criteria | ~1k |
| **fix_tickets** | AI-drafted descriptions + AC for specific tickets (keys listed below) | ~1k |
| **browse_folder** | Browse team Confluence space and summarize page structure | ~2k |

- [ ] **weekly_progress**
- [ ] **sprint_summary**
- [ ] **board_report**
- [ ] **ticket_quality**
- [ ] **fix_tickets**
- [ ] **browse_folder**

---

## Additional Tasks

_Write one task per line as a bullet point, then run `./run_command.sh`. Tasks are executed by Claude (with full Jira + Confluence access) and cleared automatically after running. Results are posted back to this page as a comment. If a task is repeatable, Claude will add it as a checkbox above._

-

---

## Configuration

**Ticket quality scope:** `sprint` _(options: sprint | backlog | all)_

**Board report — days back:** `7`

**Fix tickets — ticket keys:** _(paste keys here, comma-separated, e.g. DCPFS-12345, DCPFS-67890)_

**Create page — parent ID:** `COMMAND_PAGE_PARENT_ID_PLACEHOLDER`

---

_Run `./run_command.sh` — reads this page and executes all checked commands in order._

_Run a single command directly: `./run_command.sh --command sprint_summary`_
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
