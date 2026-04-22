# PIF Board Report — Per-Member Activity

You are running an automated workflow. Follow every step in order. Do not stop for clarification.

## Configuration

- **cloudId**: `CLOUD_ID_PLACEHOLDER`
- **project**: `PROJECT_PLACEHOLDER`
- **spaceId**: `SPACE_ID_PLACEHOLDER`
- **parentId**: `COMMAND_PAGE_PARENT_ID_PLACEHOLDER`
- **epicKeys**: `EPIC_KEYS_PLACEHOLDER`
- **weekStart**: `WEEK_START_PLACEHOLDER`
- **weekEnd**: `WEEK_END_PLACEHOLDER`
- **today**: `TODAY_PLACEHOLDER`

---

## Step 1 — Get active sprint name

Run JQL: `project = PROJECT_PLACEHOLDER AND sprint in openSprints() ORDER BY created ASC`
with `fields: ["customfield_10020"]`, `maxResults: 1`.

Extract sprint name from `customfield_10020` where `state = "active"`. Store as `SPRINT_NAME`.

Read `state/execution_plan.json` if it exists; extract `config.board_report_days` as `DAYS_BACK` (default: 7).

Print: `→ [1/5] Sprint: {SPRINT_NAME} | Reporting period: last {DAYS_BACK} days`

---

## Step 2 — Fetch PIF sprint tickets with comments

Run JQL:
```
project = PROJECT_PLACEHOLDER AND sprint in openSprints() AND "Epic Link" in (EPIC_KEYS_PLACEHOLDER)
fields: ["summary", "status", "assignee", "comment", "parent", "issuetype"]
maxResults: 100
responseContentFormat: markdown
```

Skip tickets where `issuetype.name` is `"Epic"` or `"Objective"`.

For each ticket, extract:
- `key`, `summary`, `status.name`, `assignee.displayName` (or "Unassigned")
- `parent.fields.summary` (epic name)
- ALL comments from `comment.comments[]`: for each comment, record `author.displayName`, `created` (date only), `body` (first 400 chars)
- **Recent comments** = those created within the last `DAYS_BACK` days from `WEEK_END_PLACEHOLDER`

Print: `→ [2/5] Tickets fetched: {count}`

---

## Step 3 — Group tickets by assignee

Build a map keyed by `assignee.displayName`. For each assignee, collect their tickets (tickets where they are the assignee).

For each ticket in an assignee's list:
- Note recent comments from **the assignee** (shows what they did)
- Note recent comments from **others** (shows feedback, unblocking, reviews they received)

Identify ticket disposition:
- **Done this week**: status in `[Done, Closed, Deployed]` AND at least one recent comment OR status changed recently
- **In Progress**: status = `In Progress` or `Ready for review`
- **Other**: any other status

Print: `→ [3/5] Members found: {count} — {comma-separated names}`

---

## Step 4 — Synthesize per-member summaries

For each member (sort alphabetically by last name):

Write a 2-3 sentence plain-English summary of their week:
- What did they complete?
- What are they actively working on?
- Any notable contributions (decisions made, blockers resolved, reviews given)?

Use comment text as evidence, not just ticket status. Focus on what actually happened this week based on the recent comments.

If a member has no recent comments and no status changes → write: "No activity recorded this week in ticket comments."

---

## Step 5 — Write output file

Write `output/board_report_TODAY_PLACEHOLDER.json`:

```json
{
  "command": "board_report",
  "generated_at": "{ISO timestamp}",
  "project": "PROJECT_PLACEHOLDER",
  "sprint": "{SPRINT_NAME}",
  "week": "WEEK_START_PLACEHOLDER to WEEK_END_PLACEHOLDER",
  "days_back": 7,
  "members": [
    {
      "name": "Lastname, Firstname",
      "summary": "2-3 sentence summary",
      "done": [{"key": "DCPFS-XXXXX", "summary": "...", "key_comment": "brief excerpt"}],
      "in_progress": [{"key": "DCPFS-XXXXX", "summary": "...", "key_comment": "brief excerpt"}],
      "ticket_count": {"total": 0, "done": 0, "in_progress": 0}
    }
  ]
}
```

Print: `→ [4/5] Output written`

---

## Step 6 — Create Confluence page

Build the page body:

```markdown
# PIF Board Report
## {SPRINT_NAME} | WEEK_START_PLACEHOLDER to WEEK_END_PLACEHOLDER

_Generated: TODAY_PLACEHOLDER | Source: Jira ticket comments (last {DAYS_BACK} days)_

---

### {Member Name}

**Summary:** {2-3 sentence summary of their week}

| Ticket | Summary | Status | Key Activity |
|---|---|---|---|
| [DCPFS-XXXXX](https://kroger.atlassian.net/browse/DCPFS-XXXXX) | ... | In Progress | Brief comment excerpt showing what they did |

---

### {Next Member Name}

...

---

_This report is generated from ticket comments. Activity not recorded in comments will not appear._
_Run: `./run_command.sh --command board_report`_
```

Call `createConfluencePage`:
```
cloudId: CLOUD_ID_PLACEHOLDER
spaceId: SPACE_ID_PLACEHOLDER
parentId: COMMAND_PAGE_PARENT_ID_PLACEHOLDER
title: PIF Board Report — WEEK_START_PLACEHOLDER to WEEK_END_PLACEHOLDER
body: {markdown above}
contentFormat: markdown
status: current
```

Print:
```
✅ Board report posted.
   Sprint: {SPRINT_NAME} | Week: WEEK_START_PLACEHOLDER → WEEK_END_PLACEHOLDER
   Members covered: {count}
   Page: https://kroger.atlassian.net/wiki/spaces/apiprogram/pages/{new page id}
```
