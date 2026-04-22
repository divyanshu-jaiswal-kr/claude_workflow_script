# PIF Sprint Summary — Current Sprint Overview

You are running an automated workflow. Follow every step in order. Do not stop for clarification.

## Configuration

- **cloudId**: `CLOUD_ID_PLACEHOLDER`
- **project**: `PROJECT_PLACEHOLDER`
- **spaceId**: `SPACE_ID_PLACEHOLDER`
- **parentId**: `COMMAND_PAGE_PARENT_ID_PLACEHOLDER`
- **epicKeys**: `EPIC_KEYS_PLACEHOLDER`
- **today**: `TODAY_PLACEHOLDER`

---

## Step 1 — Get active sprint name

Run JQL:
```
project = PROJECT_PLACEHOLDER AND sprint in openSprints() ORDER BY created ASC
fields: ["customfield_10020"]
maxResults: 1
```

From `customfield_10020`, find the sprint where `state = "active"`. Extract the sprint `name` (e.g., `DCP 2026Q1.6`). Store as `SPRINT_NAME`.

If no active sprint found → print `ERROR: No active sprint found.` and stop.

Print: `→ [1/5] Sprint: {SPRINT_NAME}`

---

## Step 2 — Fetch all PIF sprint tickets

Run JQL:
```
project = PROJECT_PLACEHOLDER AND sprint in openSprints() AND "Epic Link" in (EPIC_KEYS_PLACEHOLDER)
fields: ["summary", "status", "assignee", "parent", "issuetype", "priority", "labels"]
maxResults: 200
```

Skip tickets where `issuetype.name` is `"Epic"` or `"Objective"`.

For each ticket, record: `key`, `summary`, `status.name`, `assignee.displayName` (or "Unassigned"), `parent.fields.summary` (epic name), `parent.key`.

Identify **blocked tickets** as those where `status.name` equals `"Blocked"` (case-insensitive), or where any label equals `"blocked"`.

Print: `→ [2/5] Tickets fetched: {count}`

---

## Step 3 — Compute metrics

Calculate:

- **Total tickets** (all non-Epic/Objective)
- **By status**: group by `status.name`, count each group. Typical statuses: `To Do`, `In Progress`, `Ready for review`, `Closed`, `Blocked`, `Done`, `Deployed`
- **By assignee**: for each unique assignee, count total / in-progress / done (Done/Closed/Deployed)
- **By epic**: for each unique parent epic, count total / done / in-progress
- **Blocked tickets**: list of keys + summary + assignee
- **Completed this sprint**: tickets with status in `[Done, Closed, Deployed]`

Print: `→ [3/5] Metrics computed`

---

## Step 4 — Write output file

Write `output/sprint_summary_TODAY_PLACEHOLDER.json`:

```json
{
  "command": "sprint_summary",
  "generated_at": "{ISO timestamp}",
  "project": "PROJECT_PLACEHOLDER",
  "sprint": "{SPRINT_NAME}",
  "total_tickets": 0,
  "by_status": {"To Do": 0, "In Progress": 0, "Ready for review": 0, "Closed": 0, "Blocked": 0},
  "by_assignee": [
    {"name": "Lastname, Firstname", "total": 0, "in_progress": 0, "done": 0}
  ],
  "by_epic": [
    {"epic_key": "DCPFS-XXXXX", "epic_name": "...", "total": 0, "done": 0, "in_progress": 0}
  ],
  "blocked": [
    {"key": "DCPFS-XXXXX", "summary": "...", "assignee": "..."}
  ],
  "completed": [
    {"key": "DCPFS-XXXXX", "summary": "...", "assignee": "..."}
  ]
}
```

Print: `→ [4/5] Output written`

---

## Step 5 — Create Confluence page

Build the page body in markdown:

```markdown
# Sprint Summary: {SPRINT_NAME}
**Generated:** TODAY_PLACEHOLDER | **Project:** PROJECT_PLACEHOLDER

---

## At a Glance

| Metric | Count |
|---|---|
| Total tickets | {total} |
| Done / Closed / Deployed | {done count} |
| In Progress | {in_progress count} |
| Ready for Review | {review count} |
| To Do | {todo count} |
| Blocked | {blocked count} |

---

## By Team Member

| Member | Total | In Progress | Done | Blocked |
|---|---|---|---|---|
| {name} | {total} | {in_progress} | {done} | {blocked} |

---

## By Epic

| Epic | Total | Done | In Progress |
|---|---|---|---|
| {epic_name} | {total} | {done} | {in_progress} |

---

## Blocked Tickets

{If blocked list is empty: "No blocked tickets this sprint. ✅"}

| Ticket | Summary | Assignee |
|---|---|---|
| [DCPFS-XXXXX](https://kroger.atlassian.net/browse/DCPFS-XXXXX) | ... | ... |

---

## Completed This Sprint

{bullet list: - [DCPFS-XXXXX](link) — Summary (Assignee)}
```

Then call `createConfluencePage`:
```
cloudId: CLOUD_ID_PLACEHOLDER
spaceId: SPACE_ID_PLACEHOLDER
parentId: COMMAND_PAGE_PARENT_ID_PLACEHOLDER
title: PIF Sprint Summary — {SPRINT_NAME} — TODAY_PLACEHOLDER
body: {markdown above}
contentFormat: markdown
status: current
```

Print:
```
✅ Sprint summary posted.
   Sprint: {SPRINT_NAME}
   Page: https://kroger.atlassian.net/wiki/spaces/apiprogram/pages/{new page id}
```
