#!/usr/bin/env python3
"""
board_report_post.py — Build and post board report Confluence page.

Reads:  output/board_summaries.json  (Claude's output from board_report.md)
        output/board.json            (for ticket details per member)
Posts:  Confluence page under COMMAND_PAGE_PARENT_ID
"""

import os
import sys
import json
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from confluence_utils import (
    check_env, create_page, xe, h1, h2, h3, p, hr, strong, em, link, table, ul,
    jira_link, page_url, BASE_URL,
)

# ── Config from environment ───────────────────────────────────────────────────
SPACE                  = os.environ.get("SPACE", "apiprogram")
COMMAND_PAGE_PARENT_ID = os.environ.get("COMMAND_PAGE_PARENT_ID", "1112015485")
OUTPUT_DIR             = Path(__file__).parent.parent / "output"
# ─────────────────────────────────────────────────────────────────────────────

DONE_STATUSES = {"done", "closed", "deployed"}
IN_PROGRESS_STATUSES  = {"in progress", "ready for review", "in review"}


def build_page_body(summaries: dict, board_data: dict) -> str:
    """Build Confluence storage XHTML for the board report page."""
    sprint_name = xe(board_data.get("sprint_name", "Unknown Sprint"))
    fetched_at  = xe(board_data.get("fetched_at", "")[:10])
    today       = date.today().isoformat()

    # Build member → tickets map from board.json
    member_tickets: dict[str, list] = {}
    for ticket in board_data.get("tickets", []):
        assignee = ticket.get("assignee", "Unassigned")
        member_tickets.setdefault(assignee, []).append(ticket)

    parts = []
    parts.append(h1("PIF Board Report"))
    parts.append(h2(f"{board_data.get('sprint_name', '')}"))
    parts.append(p(
        f"{em(f'Generated: {today} | Source: Jira ticket comments')}"
    ))
    parts.append(hr())

    members = summaries.get("members", [])
    for member in members:
        name    = member.get("name", "Unknown")
        summary = member.get("summary", "")
        done_n  = member.get("done_count", 0)
        ip_n    = member.get("in_progress_count", 0)

        parts.append(h3(xe(name)))
        parts.append(p(f"{strong('Summary:')} {xe(summary)}"))

        # Build ticket table from board.json for this member
        tickets = member_tickets.get(name, [])
        if tickets:
            rows = []
            for t in tickets:
                status = t.get("status", "")
                recent = t.get("recent_comments", [])
                key_activity = xe(recent[0]["text"][:100]) if recent else "—"
                rows.append([
                    jira_link(t["key"]),
                    xe(t["summary"][:80]),
                    xe(status),
                    key_activity,
                ])
            parts.append(table(
                ["Ticket", "Summary", "Status", "Key Activity"],
                rows,
            ))
        else:
            parts.append(p("No tickets assigned this sprint."))

        parts.append(hr())

    parts.append(p(
        f"{em('This report is generated from ticket comments. Activity not recorded in comments will not appear.')}"
    ))
    parts.append(p(f"{em('Run: ./run_command.sh --command board_report')}"))

    return "\n".join(parts)


def main() -> None:
    check_env()

    summaries_path = OUTPUT_DIR / "board_summaries.json"
    board_path     = OUTPUT_DIR / "board.json"

    for path in (summaries_path, board_path):
        if not path.exists():
            print(f"ERROR: {path} not found.", file=sys.stderr)
            sys.exit(1)

    with open(summaries_path, encoding="utf-8") as f:
        summaries = json.load(f)
    with open(board_path, encoding="utf-8") as f:
        board_data = json.load(f)

    today = date.today().isoformat()
    sprint_name = board_data.get("sprint_name", "Unknown")

    print(f"→ Building board report page for sprint: {sprint_name}")
    body = build_page_body(summaries, board_data)

    title = f"PIF Board Report — {today}"
    print(f"→ Posting to Confluence: {title!r}")

    result = create_page(title, body, SPACE, COMMAND_PAGE_PARENT_ID)
    page_id = result["id"]

    members = summaries.get("members", [])
    print(f"\n✅ Board report posted.")
    print(f"   Sprint: {sprint_name}")
    print(f"   Members covered: {len(members)}")
    print(f"   Page: {page_url(page_id, SPACE)}")


if __name__ == "__main__":
    main()
