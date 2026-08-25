# PIF Weekly Progress — Automated Update Workflow

You are running an automated workflow. Follow every step below in order. Do not stop for clarification. Use the Atlassian MCP tools available to you.

After completing each numbered step, print a one-line progress update as shown in each step — this lets the user see live progress in the terminal.

## Configuration

- **Atlassian cloudId**: `kroger.atlassian.net`
- **Jira project**: `DCPFS`
- **Target board**: `Dec-Titans (PIF) Scrum Board` (board 4896) — PIF team tickets only
- **Confluence page ID**: `514261050`
- **Confluence space**: `apiprogram`
- **Week start (Monday)**: `WEEK_START_PLACEHOLDER`
- **Week end (today)**: `WEEK_END_PLACEHOLDER`
- **Sprint override**: `SPRINT_OVERRIDE_PLACEHOLDER`

---

## Step 1: Fetch Sprint Name (Quarter Label)

**Check if a sprint override is set first:**

If `SPRINT_OVERRIDE_PLACEHOLDER` is not empty and not the literal string `SPRINT_OVERRIDE_PLACEHOLDER`, use it directly as `QUARTER_LABEL` — skip the JQL call entirely.

Otherwise, run this JQL to get the active sprint:

```
JQL: project = DCPFS AND sprint in openSprints() ORDER BY created ASC
maxResults: 1
fields: ["customfield_10020"]
```

From the result, find the sprint in `customfield_10020` where `state = "active"`. Extract:
- **Quarter label**: the sprint `name` field (e.g., `DCP 2026Q1.6`)

Format the week range for display using ordinal suffixes:
- `WEEK_START_PLACEHOLDER` → e.g., `13th April 2026`
- `WEEK_END_PLACEHOLDER` → e.g., `19th April 2026`

Ordinal rules: 1st, 2nd, 3rd, 4th–20th→th, 21st, 22nd, 23rd, 24th–30th→th/st/nd/rd.

Store as: `QUARTER_LABEL`, `WEEK_START_DISPLAY`, `WEEK_END_DISPLAY`.

Write `output/sprint_info.json`:
```json
{
  "name": "DCP 2026Q1.6",
  "week_start": "WEEK_START_PLACEHOLDER",
  "week_end": "WEEK_END_PLACEHOLDER",
  "week_start_display": "13th April 2026",
  "week_end_display": "19th April 2026"
}
```

**Print after this step:**
```
→ [1/9] Sprint: {QUARTER_LABEL} | Week: {WEEK_START_DISPLAY} - {WEEK_END_DISPLAY}
```

If no sprint is found and no override is set → print `ERROR: No active sprint found in DCPFS` and stop.

---

## Step 2: Discover PIF Team Epics

Run:
```
JQL: project = DCPFS AND issuetype = Epic AND status not in (Closed, Done) AND "Team[Team]" = "18d9661f-511b-4e04-8bd8-cb82f16f27e0"
fields: ["summary", "status", "key"]
maxResults: 30
```

This filters by the Dec-Titans (PIF) Atlassian Team field, not by name pattern — it automatically picks up the current quarter's epics without any hardcoded keys. Collect the `key` values of all epics returned and store as `EPIC_KEYS`.

**Print after this step:**
```
→ [2/9] PIF epics: {count} keys — {comma-separated list}
```

If epic count is 0 → print `ERROR: No PIF epics found` and stop.

---

## Step 3: Fetch PIF Tickets Updated This Week

Use `QUARTER_LABEL` (from Step 1) as the sprint name — this correctly handles both the active sprint and any sprint override.

Fetch non-Todo tickets updated since `WEEK_START_PLACEHOLDER`:

```
JQL: project = DCPFS AND sprint = "{QUARTER_LABEL}" AND status != "To Do" AND updated >= "WEEK_START_PLACEHOLDER" AND "Epic Link" in ({EPIC_KEYS comma-separated})
maxResults: 100
fields: ["summary", "description", "status", "parent", "comment", "assignee", "issuetype"]
responseContentFormat: markdown
```

If this returns 0 results, fall back to (no date filter):
```
JQL: project = DCPFS AND sprint = "{QUARTER_LABEL}" AND status != "To Do" AND "Epic Link" in ({EPIC_KEYS comma-separated})
```

For each ticket, extract:
- `key`, `summary`, `status.name`, `assignee.displayName`
- `parent.fields.summary` (epic name), `parent.key`
- `description` (first 400 chars)
- Latest 3 comments from `comment.comments` (most recent first, 200 chars each)

Skip tickets where `issuetype.name` is `"Epic"` or `"Objective"`.

Group by parent epic summary into `TICKETS_BY_EPIC` (a map of epic name → list of tickets). Tickets with no parent go under `"General / Unepic Work"`.

Write `output/tickets_by_epic.json` with this structure:
```json
{
  "Improve Catalog V2 platform reliability and performance by 50%": {
    "epic_key": "DCPFS-29174",
    "tickets": [
      {
        "key": "DCPFS-XXXXX",
        "summary": "...",
        "status": "In Progress",
        "assignee": "...",
        "description": "...",
        "comments": ["most recent comment text", "second", "third"]
      }
    ]
  }
}
```

**Print after this step:**
```
→ [3/9] Tickets fetched: {total count} across {epic count} epics{" (fallback: no date filter)" if fallback used}
```

---

## Step 4: Fetch Current Confluence Page — Read Last Week's Data

```
tool: getConfluencePage
cloudId: kroger.atlassian.net
pageId: 514261050
contentFormat: markdown
```

If this fails → print `ERROR: Could not fetch Confluence page` and stop.

**CRITICAL:** Store the ENTIRE page body exactly as returned — this includes all previous week sections. Do not truncate. You will prepend the new section to this full body in Step 7.

From the page body:
1. **Store the complete, unmodified body** as `CURRENT_PAGE_BODY` — preserve every line including all previous sprints and history.
2. **Find the first markdown table** in the body — this is last week's update.
3. **Parse every data row** of that table (skip the header row `| Service | Progress | ...`).
   For each row extract: Service name, Progress text, Next Steps text, Blocker/Targets text.
4. Store as `LAST_WEEK_DATA` — a list of objects: `{service, progress, next_steps, blockers}`.

Write `output/last_week.json`:
```json
[
  {
    "service": "Catalog V2_Q1 Iterative tech enhancements",
    "progress": "full text of last week's progress cell",
    "next_steps": "full text of last week's next steps cell",
    "blockers": "full text of last week's blockers cell"
  }
]
```

**Print after this step:**
```
→ [4/9] Confluence page fetched | Last week table: {N} epic rows parsed — {comma-separated service names}
```

---

## Step 5: Synthesize Per-Epic Table Rows — No-Repeat Rule

For each epic in `TICKETS_BY_EPIC`, generate one table row. Use `LAST_WEEK_DATA` to ensure you do not duplicate content from the previous week.

### How to apply the no-repeat rule

**Before writing any cell for an epic**, find the matching entry in `LAST_WEEK_DATA` where `service` equals the epic name (case-insensitive). Call it `PREV` (may be empty/null if this is a new epic or first run).

#### Progress cell

Write **only new information** — content NOT already covered in `PREV.progress`:

- **Newly completed tickets**: Only mention if they finished THIS week (i.e., not described as complete/done in `PREV.progress`). Use ticket status = Done/Closed/Deployed + recent comments as evidence.
- **Active work**: Only describe what has meaningfully advanced since last week. If a ticket appears to be in the same state as last week (same status, no new comments), skip it or note it in one phrase (e.g., "continues in review").
- **New highlights**: Deployments, resolved blockers, test results, or PR merges mentioned in THIS week's comments that do not appear in `PREV.progress`.
- If nothing substantively changed since last week, write exactly: `No significant updates this week.`
- 3–5 sentences max. Plain text, no bullet points.

#### Next Steps cell

- Write what's coming next based on in-progress/open tickets and comment language ("next", "plan", "will", "upcoming").
- If `PREV.next_steps` lists actions that are **still pending** (not yet done or in-progress), do NOT copy them verbatim. Instead write: `Still pending from last week: {brief summary}. Additionally: {any new next steps}.`
- If `PREV.next_steps` listed actions that are **now completed or in-progress**, replace them with what comes after.
- 2–3 sentences max.

#### Blockers / Targets cell

- **New blockers**: Include any new blockers, APT requests, dependencies, or infra issues NOT in `PREV.blockers`.
- **Ongoing blockers**: If a blocker from `PREV.blockers` is still unresolved, write: `[Ongoing] {brief blocker description}` — do not write it as if it's new.
- **Resolved blockers**: If a blocker from `PREV.blockers` is now resolved (mentioned in comments), do not include it.
- If no blockers: leave as empty string `""`.

**Print after each epic is synthesized:**
```
→ [5/9] Synthesizing: {epic name} ({ticket count} tickets)
```

**Print after all epics:**
```
→ [5/9] Synthesis complete — {N} epic rows generated
```

---

## Step 6: Build the New Confluence Section

Compose this markdown block:

```markdown
### {QUARTER_LABEL}

### {WEEK_START_DISPLAY} - {WEEK_END_DISPLAY}

| Service | Progress | Next Steps | Blocker/ Targets |   |
| --- | --- | --- | --- | --- |
| {epic_name_1} | {progress_1} | {next_steps_1} | {blockers_1} |   |
| {epic_name_2} | {progress_2} | {next_steps_2} | {blockers_2} |   |

‌

```

Formatting rules:
- Use the **exact** epic name from Jira (`parent.fields.summary`) as the Service value
- Each distinct update, ticket, or action item goes on its own line — separate them with `<br>` so Confluence renders each as its own line with clear visual spacing
- Do not run multiple items into one paragraph or sentence — one item per line
- Keep each cell under ~400 characters total
- The `‌` character (zero-width non-joiner) and trailing blank line match the existing page format

Example of correct cell formatting (Progress cell):
```
Loader repo separated into 4 independently deployable units<br>Validated Catalog V2 Store Layer changes<br>Deployed to prod and verified
```

Example of correct Next Steps cell:
```
Alert when item count drops by 25% for a location<br>Complete store layer validation<br>Run data parity testing script
```

Write `output/new_section.json`:
```json
{
  "quarter_label": "DCP 2026Q1.6",
  "week_range": "13th April 2026 - 19th April 2026",
  "rows": [
    {
      "service": "...",
      "progress": "...",
      "next_steps": "...",
      "blockers": ""
    }
  ]
}
```

**Print after this step:**
```
→ [6/9] New section built — {N} rows
```

---

## Step 7: Build Updated Page Body

**CRITICAL:** Preserve all history. Concatenate in this exact order:

```
{NEW_SECTION}

{CURRENT_PAGE_BODY}
```

Where:
- `{NEW_SECTION}` is the new table you built in Step 6
- `{CURRENT_PAGE_BODY}` is the ENTIRE original page body from Step 4 (all previous weeks, untouched)

The result must include:
- The new DCP 2026Q1.X section at the top
- Every previous week section below it
- All page content that existed before this run

**Print after this step:**
```
→ [7/9] Page body assembled (NEW_SECTION prepended to {number of characters} bytes of history)
```

---

## Step 8: Publish to Confluence

**Before publishing:** Verify that the body from Step 7 contains:
- At least 3 previous week sections (from prior runs)
- All "DCP 2026" headers from the original page
- Zero truncation — the body should be several thousand characters long

If the body appears truncated or too small, print `ERROR: Body truncation detected. Refusing to publish.` and stop.

Publish only if the body contains all history:

```
tool: updateConfluencePage
cloudId: kroger.atlassian.net
pageId: 514261050
title: PIF Weekly Progress 2026
body: {complete updated body from Step 7 — must include all history}
contentFormat: markdown
status: current
```

If a version conflict error occurs, fetch the page again to get the latest version and retry once.

**Print after this step:**
```
→ [8/9] Confluence page updated (body size: {bytes} including all history)
```

---

## Step 9: Confirm

Print:
```
✅ Done.
Sprint:          {QUARTER_LABEL}
Week:            {WEEK_START_DISPLAY} - {WEEK_END_DISPLAY}
Epics covered:   {count}
Tickets read:    {count}
URL: https://kroger.atlassian.net/wiki/spaces/apiprogram/pages/514261050/PIF+Weekly+Progress+2026
```
