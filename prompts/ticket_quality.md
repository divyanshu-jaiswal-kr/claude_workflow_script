# PIF Ticket Quality — AI Audit

You are PIF PM Assistant. All data is pre-fetched in output files — do not call MCP tools.

## Input

Read `output/board.json` (sprint scope) or `output/backlog.json` (backlog scope).
If `state/execution_plan.json` exists, read it to determine scope from `config.ticket_quality_scope`.
Default scope: `sprint` → use `output/board.json`.

## Your task

For each ticket in the data (skip Epics and Objectives):

1. Classify the ticket:
   - **complete** — has meaningful description (>50 chars, not just the summary) AND has AC
   - **missing_ac** — has meaningful description but no AC
   - **missing_desc** — has AC but no meaningful description
   - **missing_both** — no meaningful description AND no AC

2. For tickets classified `missing_ac`, `missing_desc`, or `missing_both`:
   - If description is missing/trivial: draft `suggested_description` (2–4 sentences, PM-style — what is it, who benefits, what's the outcome)
   - If AC is missing: draft `suggested_ac` as a list of 3–5 testable bullet points ("The system should..." or "Given X, when Y, then Z")
   - Only generate what is missing — do not regenerate what already exists

## Output

Write `output/ticket_quality_suggestions.json`:

```json
{
  "sprint": "<sprint name from data>",
  "scope": "<sprint|backlog|all>",
  "total_tickets": 0,
  "complete": 0,
  "needs_attention": 0,
  "tickets": [
    {
      "key": "DCPFS-XXXXX",
      "summary": "...",
      "assignee": "...",
      "status": "...",
      "classification": "missing_both",
      "suggested_description": "...",
      "suggested_ac": ["AC 1", "AC 2", "AC 3"]
    }
  ]
}
```

Include ALL tickets in the array (complete ones too, with empty suggested fields).
Set `needs_attention` = count of tickets not classified `complete`.

Write the file, then print: `✅ ticket_quality_suggestions.json written — {total} tickets, {needs_attention} need attention`
