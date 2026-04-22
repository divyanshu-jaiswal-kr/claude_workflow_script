#!/usr/bin/env python3
"""
fetch_board.py — Fetch PIF sprint tickets with full details: description, AC, and all comments.

Writes: output/board.json
Used by: board_report.md (Claude), ticket_quality.md (Claude), fix_tickets.md (Claude)
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from confluence_utils import check_env, now_iso

import requests
from base64 import b64encode

# ── Config from environment ───────────────────────────────────────────────────
BASE_URL   = os.environ.get("ATLASSIAN_BASE_URL", "https://kroger.atlassian.net")
EMAIL      = os.environ.get("ATLASSIAN_EMAIL", "")
TOKEN      = os.environ.get("ATLASSIAN_API_TOKEN", "")
PROJECT    = os.environ.get("PROJECT", "DCPFS")
EPIC_KEYS  = os.environ.get("EPIC_KEYS", "DCPFS-27809,DCPFS-27807,DCPFS-27772,DCPFS-27778")
AC_FIELD   = os.environ.get("AC_FIELD", "customfield_10147")
OUTPUT_DIR = Path(__file__).parent.parent / "output"
# ─────────────────────────────────────────────────────────────────────────────


def auth_header() -> dict:
    creds = b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def jira_search(jql: str, fields: list[str], max_results: int = 100) -> list:
    """Paginated Jira issue search."""
    url = f"{BASE_URL}/rest/api/3/issue/search"
    all_issues, start = [], 0
    while True:
        resp = requests.get(url, headers=auth_header(), params={
            "jql": jql,
            "fields": ",".join(fields),
            "maxResults": max_results,
            "startAt": start,
        })
        resp.raise_for_status()
        data = resp.json()
        chunk = data.get("issues", [])
        all_issues.extend(chunk)
        start += len(chunk)
        if start >= data.get("total", 0):
            break
    return all_issues


def get_sprint_name() -> str:
    issues = jira_search(
        jql=f"project = {PROJECT} AND sprint in openSprints()",
        fields=["customfield_10020"],
        max_results=1,
    )
    if not issues:
        raise RuntimeError(f"No open sprint found in {PROJECT}.")
    for sprint in issues[0]["fields"].get("customfield_10020", []):
        if sprint.get("state") == "active":
            return sprint["name"]
    raise RuntimeError("No active sprint found.")


def extract_adf_text(node) -> str:
    """Recursively extract plain text from ADF node."""
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    return " ".join(filter(None, (extract_adf_text(c) for c in node.get("content", []))))


def parse_field(field) -> str:
    """Parse a Jira field that may be ADF, string, or None."""
    if field is None:
        return ""
    if isinstance(field, dict):
        return extract_adf_text(field).strip()
    return str(field).strip()


def parse_comment_date(date_str: str) -> str:
    """Return YYYY-MM-DD from Jira ISO timestamp."""
    try:
        return date_str[:10]
    except Exception:
        return date_str


def main() -> None:
    if not EMAIL or not TOKEN:
        print("ERROR: ATLASSIAN_EMAIL and ATLASSIAN_API_TOKEN must be set.", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("→ Fetching active sprint name...")
    sprint_name = get_sprint_name()
    print(f"   Sprint: {sprint_name}")

    print("→ Fetching PIF sprint tickets (full details)...")
    epic_csv = ", ".join(k.strip() for k in EPIC_KEYS.split(","))
    jql = (
        f'project = {PROJECT} AND sprint in openSprints() '
        f'AND "Epic Link" in ({epic_csv})'
    )
    fields = [
        "summary", "description", "status", "assignee", "parent",
        "issuetype", "customfield_10020", "customfield_10032",
        AC_FIELD,  # Acceptance Criteria
        "comment", "labels", "priority",
    ]
    issues = jira_search(jql, fields)
    print(f"   Raw issues: {len(issues)}")

    tickets = []
    for issue in issues:
        f = issue["fields"]

        if f.get("issuetype", {}).get("name", "") in ("Epic", "Objective"):
            continue

        key      = issue["key"]
        summary  = f.get("summary", "")
        status   = f.get("status", {}).get("name", "Unknown")
        assignee = (f.get("assignee") or {}).get("displayName", "Unassigned")
        labels   = f.get("labels") or []

        parent      = f.get("parent") or {}
        epic_key    = parent.get("key", "N/A")
        epic_name   = (parent.get("fields") or {}).get("summary", "Unepic Work")

        description = parse_field(f.get("description"))[:1000]
        ac          = parse_field(f.get(AC_FIELD))[:1000]

        sp_raw = f.get("customfield_10032")
        story_points = int(sp_raw) if isinstance(sp_raw, (int, float)) else None

        # All comments
        raw_comments = (f.get("comment") or {}).get("comments", [])
        comments = []
        for c in raw_comments:
            comments.append({
                "author": (c.get("author") or {}).get("displayName", "Unknown"),
                "date":   parse_comment_date(c.get("created", "")),
                "text":   parse_field(c.get("body", ""))[:400],
            })

        # Recent comments (last 7 days)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        recent_comments = [c for c in comments if c["date"] >= cutoff]

        tickets.append({
            "key": key,
            "summary": summary,
            "status": status,
            "assignee": assignee,
            "epic_key": epic_key,
            "epic_name": epic_name,
            "description": description,
            "ac": ac,
            "story_points": story_points,
            "labels": labels,
            "recent_comments": recent_comments,
            "all_comments": comments,
        })

    output = {
        "fetched_at": now_iso(),
        "sprint_name": sprint_name,
        "project": PROJECT,
        "epic_keys": EPIC_KEYS,
        "ac_field": AC_FIELD,
        "ticket_count": len(tickets),
        "tickets": tickets,
    }

    out_path = OUTPUT_DIR / "board.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)

    print(f"✓ Written: {out_path}")
    print(f"  Tickets: {len(tickets)}")


if __name__ == "__main__":
    main()
