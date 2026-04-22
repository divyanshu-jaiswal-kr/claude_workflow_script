#!/usr/bin/env python3
"""
fetch_sprint.py — Fetch PIF active sprint tickets and compute metrics.

Writes: output/sprint.json
Used by: sprint_summary_post.py (no Claude needed)
"""

import os
import sys
import json
from datetime import datetime, timezone
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

DONE_STATUSES = {"done", "closed", "deployed"}
IN_PROGRESS_STATUSES = {"in progress", "ready for review", "in review"}
# ─────────────────────────────────────────────────────────────────────────────


def auth_header() -> dict:
    creds = b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def jira_search(jql: str, fields: list[str], max_results: int = 200) -> list:
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
    """Return the name of the currently active sprint."""
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


def fetch_sprint_tickets() -> list:
    """Fetch all non-Epic/Objective PIF tickets in the active sprint."""
    epic_csv = ", ".join(k.strip() for k in EPIC_KEYS.split(","))
    jql = (
        f'project = {PROJECT} AND sprint in openSprints() '
        f'AND "Epic Link" in ({epic_csv})'
    )
    fields = [
        "summary", "status", "assignee", "parent", "issuetype",
        "customfield_10020",  # Sprint
        "customfield_10032",  # Story Points
        "labels", "priority",
    ]
    return jira_search(jql, fields)


def extract_adf_text(node) -> str:
    """Recursively extract plain text from ADF node."""
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    return " ".join(filter(None, (extract_adf_text(c) for c in node.get("content", []))))


def main() -> None:
    if not EMAIL or not TOKEN:
        print("ERROR: ATLASSIAN_EMAIL and ATLASSIAN_API_TOKEN must be set.", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("→ Fetching active sprint name...")
    sprint_name = get_sprint_name()
    print(f"   Sprint: {sprint_name}")

    print("→ Fetching PIF sprint tickets...")
    issues = fetch_sprint_tickets()
    print(f"   Raw issues returned: {len(issues)}")

    # ── Process tickets ───────────────────────────────────────────────────────
    tickets = []
    by_status: dict[str, int] = {}
    by_assignee: dict[str, dict] = {}
    by_epic: dict[str, dict] = {}

    for issue in issues:
        f = issue["fields"]

        # Skip Epics and Objectives
        if f.get("issuetype", {}).get("name", "") in ("Epic", "Objective"):
            continue

        key      = issue["key"]
        summary  = f.get("summary", "")
        status   = f.get("status", {}).get("name", "Unknown")
        assignee = (f.get("assignee") or {}).get("displayName", "Unassigned")
        labels   = [lbl for lbl in (f.get("labels") or [])]

        # Epic info from parent
        parent      = f.get("parent") or {}
        epic_key    = parent.get("key", "N/A")
        epic_name   = (parent.get("fields") or {}).get("summary", "Unepic Work")

        # Story points
        sp_raw = f.get("customfield_10032")
        story_points = int(sp_raw) if isinstance(sp_raw, (int, float)) else None

        ticket = {
            "key": key,
            "summary": summary,
            "status": status,
            "assignee": assignee,
            "epic_key": epic_key,
            "epic_name": epic_name,
            "story_points": story_points,
            "labels": labels,
        }
        tickets.append(ticket)

        # by_status
        by_status[status] = by_status.get(status, 0) + 1

        # by_assignee
        if assignee not in by_assignee:
            by_assignee[assignee] = {"name": assignee, "total": 0, "in_progress": 0, "done": 0, "blocked": 0}
        by_assignee[assignee]["total"] += 1
        sl = status.lower()
        if sl in DONE_STATUSES:
            by_assignee[assignee]["done"] += 1
        elif sl in IN_PROGRESS_STATUSES:
            by_assignee[assignee]["in_progress"] += 1
        elif sl == "blocked":
            by_assignee[assignee]["blocked"] += 1

        # by_epic
        if epic_key not in by_epic:
            by_epic[epic_key] = {"epic_key": epic_key, "epic_name": epic_name, "total": 0, "done": 0, "in_progress": 0}
        by_epic[epic_key]["total"] += 1
        if sl in DONE_STATUSES:
            by_epic[epic_key]["done"] += 1
        elif sl in IN_PROGRESS_STATUSES:
            by_epic[epic_key]["in_progress"] += 1

    blocked   = [t for t in tickets if t["status"].lower() in ("blocked",) or "blocked" in [l.lower() for l in t["labels"]]]
    completed = [t for t in tickets if t["status"].lower() in DONE_STATUSES]

    output = {
        "fetched_at": now_iso(),
        "sprint_name": sprint_name,
        "project": PROJECT,
        "total_tickets": len(tickets),
        "by_status": by_status,
        "by_assignee": sorted(by_assignee.values(), key=lambda x: x["name"]),
        "by_epic": sorted(by_epic.values(), key=lambda x: x["epic_name"]),
        "blocked": [{"key": t["key"], "summary": t["summary"], "assignee": t["assignee"]} for t in blocked],
        "completed": [{"key": t["key"], "summary": t["summary"], "assignee": t["assignee"]} for t in completed],
    }

    out_path = OUTPUT_DIR / "sprint.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)

    print(f"✓ Written: {out_path}")
    print(f"  Total: {len(tickets)} | Done: {len(completed)} | Blocked: {len(blocked)}")


if __name__ == "__main__":
    main()
