# PIF Dispatcher — Parse Command Page and Build Execution Plan

You are running an automated workflow. Follow every step in order. Do not stop for clarification.

## Configuration

- **cloudId**: `CLOUD_ID_PLACEHOLDER`
- **commandPageId**: `COMMAND_PAGE_ID_PLACEHOLDER`
- **stateFile**: `state/execution_plan.json`

---

## Step 1 — Read the command page

Call `getConfluencePage`:
```
cloudId: CLOUD_ID_PLACEHOLDER
pageId: COMMAND_PAGE_ID_PLACEHOLDER
contentFormat: markdown
```

Store the full page body as `PAGE_BODY`. Store the page title.

Print:
```
→ [Dispatcher] Command page fetched.
```

---

## Step 2 — Parse checked commands

Scan `PAGE_BODY` line by line. A command is checked when the line matches this exact pattern:
```
- [x] **<command_name>**
```
(case-insensitive for the `x`, the command name is lowercase snake_case)

Collect all checked command names in order of appearance. Valid command names are:
`weekly_progress`, `sprint_summary`, `board_report`, `ticket_quality`, `fix_descriptions`, `browse_folder`

If a line matches `- [ ] **<command_name>**` (unchecked), skip it.

Print:
```
→ [Dispatcher] Checked commands: {comma-separated list, or "none"}
```

---

## Step 3 — Parse configuration values

From `PAGE_BODY`, extract configuration values using these exact patterns:

| Config key | Page pattern to match |
|---|---|
| `ticket_quality_scope` | Line containing `**Ticket quality scope:**` — extract value inside backticks |
| `board_report_days` | Line containing `**Board report — days back:**` — extract number inside backticks |
| `fix_descriptions_keys` | Line containing `**Fix descriptions — ticket keys:**` — extract text after the colon (may not have backticks; comma-separated keys like DCPFS-XXXXX) |
| `create_page_parent` | Line containing `**Create page — parent ID:**` — extract number inside backticks |

Use these defaults if a value is missing or unparseable:
- `ticket_quality_scope`: `"sprint"`
- `board_report_days`: `7`
- `fix_descriptions_keys`: `""`
- `create_page_parent`: `"COMMAND_PAGE_PARENT_ID_PLACEHOLDER"`

Print:
```
→ [Dispatcher] Config parsed: scope={ticket_quality_scope} | days={board_report_days} | fix_keys={fix_descriptions_keys or "(none)"}
```

---

## Step 4 — Write execution plan

Write the file `state/execution_plan.json` using the Write tool:

```json
{
  "generated_at": "{current ISO timestamp}",
  "commands": ["{checked command 1}", "{checked command 2}"],
  "config": {
    "ticket_quality_scope": "{value}",
    "board_report_days": {number},
    "fix_descriptions_keys": "{comma-separated keys or empty string}",
    "create_page_parent": "{page ID}"
  }
}
```

If no commands are checked, write `"commands": []`.

Print:
```
→ [Dispatcher] Execution plan written to state/execution_plan.json
```

---

## Step 5 — Reset command page checkboxes and update last-run timestamp

Build an updated version of `PAGE_BODY`:

1. Replace every `- [x] **` with `- [ ] **` (uncheck all checked commands)
2. Find the line starting with `> **Last run:**` and replace it with:
   `> **Last run:** {current date and time, e.g. "2026-04-22 14:30 ET"}`

Then call `updateConfluencePage`:
```
cloudId: CLOUD_ID_PLACEHOLDER
pageId: COMMAND_PAGE_ID_PLACEHOLDER
title: PIF Automation Commands
body: {updated PAGE_BODY}
contentFormat: markdown
status: current
```

Print:
```
→ [Dispatcher] Command page reset. Last run timestamp updated.
```

---

## Step 6 — Summary

Print:
```
✅ [Dispatcher] Done.
   Commands queued: {count} — {list}
   Execution plan: state/execution_plan.json
```

If commands list is empty, print:
```
ℹ️  [Dispatcher] No commands checked on the command page. Nothing to run.
```
