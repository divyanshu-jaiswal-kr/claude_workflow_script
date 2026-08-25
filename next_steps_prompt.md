# PIF Next Sprint — Next Steps Auto-Update

You are running an automated workflow. Follow every step in order. Do not stop for clarification. Use the Atlassian MCP tools available to you.

After completing each numbered step, print a one-line progress update as shown.

## Configuration

- **cloudId**: `kroger.atlassian.net`
- **Jira project**: `DCPFS`
- **Confluence page ID**: `514261050`
- **PIF epic keys**: resolved dynamically in Step 1.5 — do not hardcode, they rotate every quarter
- **Today**: `TODAY_PLACEHOLDER`

---

## Step 1: Find Active Sprint

```
JQL: project = DCPFS AND sprint in openSprints() ORDER BY created ASC
fields: ["customfield_10020"]
maxResults: 1
```

From `customfield_10020`, find the entry where `state = "active"`. Extract its `name` (e.g., `DCP 2026Q1.6`). Store as `ACTIVE_SPRINT`.

**Print:** `→ [1/7] Active sprint: {ACTIVE_SPRINT}`

If not found → print `ERROR: No active sprint found in DCPFS` and stop.

---

## Step 1.5: Discover PIF Team Epics

Run:
```
JQL: project = DCPFS AND issuetype = Epic AND status not in (Closed, Done) AND "Team[Team]" = "18d9661f-511b-4e04-8bd8-cb82f16f27e0"
fields: ["summary", "status", "key"]
maxResults: 30
```

This filters by the Dec-Titans (PIF) Atlassian Team field, not by name pattern — it automatically picks up the current quarter's epics without any hardcoded keys. Collect the `key` and `summary` of all epics returned and store as `EPIC_KEYS` (list of `{key, summary}`).

If epic count is 0 → print `ERROR: No PIF epics found` and stop.

**Print:** `→ [1.5/7] PIF epics: {count} keys — {comma-separated list}`

---

## Step 2: Determine Next Sprint Name

Parse `ACTIVE_SPRINT` by splitting on `.` and incrementing the last segment by 1.

Examples:
- `DCP 2026Q1.6` → `DCP 2026Q1.7`
- `DCP 2026Q1.9` → `DCP 2026Q1.10`

Store as `NEXT_SPRINT`.

Now verify it exists — run any JQL against it to confirm:
```
JQL: project = DCPFS AND sprint = "{NEXT_SPRINT}" ORDER BY created ASC
fields: ["summary"]
maxResults: 1
```

If 0 results → print `INFO: Next sprint {NEXT_SPRINT} not yet created in Jira. Nothing to update.` and stop (this is normal, not an error — exit code 0).

**Print:** `→ [2/7] Next sprint: {NEXT_SPRINT}`

---

## Step 3: Fetch Open PIF Tickets from Next Sprint

```
JQL: project = DCPFS AND sprint = "{NEXT_SPRINT}" AND status = "Open" AND "Epic Link" in ({EPIC_KEYS keys, comma-separated})
fields: ["summary", "status", "parent", "issuetype", "assignee"]
maxResults: 100
```

If this returns 0 results, retry without the Epic Link filter and then filter manually by parent key:
```
JQL: project = DCPFS AND sprint = "{NEXT_SPRINT}" AND status = "Open"
```

**Skip** any ticket where `issuetype.name` is `"Epic"`, `"Objective"`, or `"Task"`, or where the summary contains `"Sprint Goal"`.

Group the remaining tickets by their `parent.key`. Use `parent.fields.summary` (the epic's actual Jira summary) as the service label — do not use a static name map. Tickets whose `parent.key` is not in `EPIC_KEYS` are ignored.

Store as `TICKETS_BY_SERVICE` (map of service label → list of ticket summaries).

**Print:** `→ [3/7] Open tickets in {NEXT_SPRINT}: {total} across {service count} services`

---

## Step 4: Fetch Current Confluence Page

```
tool: getConfluencePage
cloudId: kroger.atlassian.net
pageId: 514261050
contentFormat: markdown
```

**CRITICAL:** Store the ENTIRE page body exactly as returned — every line, every section, every previous sprint entry. Do not truncate or summarise. Store as `CURRENT_BODY`.

**Print:** `→ [4/7] Confluence page fetched ({character count} chars)`

If this fails → print `ERROR: Could not fetch Confluence page` and stop.

---

## Step 5: Build Next Steps Cell Content Per Service

For each service present in `TICKETS_BY_SERVICE`, build the replacement text for the Next Steps cell:

- Take all ticket summaries for that service from `TICKETS_BY_SERVICE`.
- Format: each ticket summary on its own line, separated by `<br>` — this renders as a clean individual line per ticket in Confluence with proper visual spacing.
- Do NOT join tickets into a paragraph or run them together as one sentence.
- **If a service has no open tickets in `NEXT_SPRINT`, do NOT replace its Next Steps cell at all — leave the existing content untouched.**

Example output for a service with 3 tickets:
```
Implement POST /uploads API<br>Enable Azure blob storage access<br>Arrive at file meta table schema
```

This renders in Confluence as:
```
Implement POST /uploads API
Enable Azure blob storage access
Arrive at file meta table schema
```

**Print:** `→ [5/7] Next Steps content built for {service count} services ({N} cells will be updated, others left unchanged)`

---

## Step 6: Update First Table in Page Body — Preserve All History

**CRITICAL:** `UPDATED_BODY` must be a copy of `CURRENT_BODY` with only the Next Steps cells of the first table modified. Every other line — all previous sprint sections, all other tables, all history — must be preserved byte-for-byte.

Steps:
1. Locate the **first markdown table** in `CURRENT_BODY` (header row contains `| Service | Progress | Next Steps | Blocker/ Targets |`) — this is the most recent week's entry.
2. For each data row in that first table only:
   - Check if the `Service` cell matches one of the 4 service labels (case-insensitive, partial match ok).
   - If it matches AND that service has replacement content from Step 5, **replace only the `Next Steps` cell** (column index 2, 0-based).
   - If the service has no replacement content (no open tickets), **leave the cell exactly as-is**.
   - Leave `Progress` and `Blocker/ Targets` columns untouched in all rows.
3. Everything outside the first table (all previous sprints, all other content) is copied verbatim — do not touch it.

Store the result as `UPDATED_BODY`. Its length must be close to `CURRENT_BODY`'s length (only the Next Steps text changed).

**Before continuing:** Verify that `UPDATED_BODY` contains multiple sprint sections (not just the first table). If it appears truncated, print `ERROR: Body truncation detected — aborting to protect page history` and stop.

**Print:** `→ [6/7] Next Steps cells updated ({N} cells changed) | Body: {UPDATED_BODY length} chars`

---

## Step 7: Publish to Confluence

**Before publishing:** Confirm that `UPDATED_BODY` is at least 80% the length of `CURRENT_BODY`. If shorter, print `ERROR: Body too short — refusing to publish to protect history` and stop.

```
tool: updateConfluencePage
cloudId: kroger.atlassian.net
pageId: 514261050
title: PIF Weekly Progress 2026
body: {UPDATED_BODY}
contentFormat: markdown
status: current
versionMessage: "Auto-update: {NEXT_SPRINT} open tickets → Next Steps (TODAY_PLACEHOLDER)"
```

If a version conflict error occurs, fetch the page again and retry once.

**Print:** `→ [7/7] Confluence page published`

Print final summary:
```
✅ Done — Next Steps updated with {NEXT_SPRINT} open tickets
Active sprint:   {ACTIVE_SPRINT}
Next sprint:     {NEXT_SPRINT}
Tickets added:   {total count}
URL: https://kroger.atlassian.net/wiki/spaces/apiprogram/pages/514261050/PIF+Weekly+Progress+2026
```
