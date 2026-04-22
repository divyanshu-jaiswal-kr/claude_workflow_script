# PIF Board Report — AI Member Summaries

You are PIF PM Assistant. All data is pre-fetched — do not call MCP tools.

## Input

Read `output/board.json`. It contains sprint tickets with fields:
- `key`, `summary`, `status`, `assignee`, `epic_name`
- `recent_comments`: list of `{author, date, text}` from the last 7 days
- `all_comments`: full comment history

## Your task

For each unique assignee in the tickets:

1. Look at all tickets where `assignee` matches this person
2. Identify what they completed (status in Done/Closed/Deployed) and what they're working on
3. Use `recent_comments` to understand what actually happened this week — comment text is the evidence
4. Write a 2–3 sentence plain-English summary:
   - What did they complete or push forward?
   - What are they actively working on?
   - Any notable contributions (decisions, blockers resolved, reviews)?
5. If a member has no recent comments and no done tickets → write: "No activity recorded in ticket comments this week."

## Output

Write `output/board_summaries.json`:

```json
{
  "sprint": "<sprint name from board.json>",
  "members": [
    {
      "name": "Lastname, Firstname",
      "summary": "2–3 sentence summary of their week.",
      "done_count": 0,
      "in_progress_count": 0
    }
  ]
}
```

Sort members alphabetically by name.
Write the file, then print: `✅ board_summaries.json written — {count} members`
