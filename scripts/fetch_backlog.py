#!/usr/bin/env python3
"""
fetch_backlog.py — Fetch PIF backlog tickets (To Do, not in active sprint).

Writes: output/backlog.json
Used by: ticket_quality.md (Claude) when scope=backlog or scope=all
"""

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from confluence_utils import now_iso

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


def jira_search(jql: str, fields: list[str], max_results: int = 200) -> list:
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


def extract_adf_text(node) -> str:
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    return " ".join(filter(None, (extract_adf_text(c) for c in node.get("content", []))))


def parse_field(field) -> str:
    if field is None:
        return ""
    if isinstance(field, dict):
        return extract_adf_text(field).strip()
    return str(field).strip()


def main() -> None:
    if not EMAIL or not TOKEN:
        print("ERROR: ATLASSIAN_EMAIL and ATLASSIAN_API_TOKEN must be set.", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("→ Fetching PIF backlog tickets...")
    epic_csv = ", ".join(k.strip() for k in EPIC_KEYS.split(","))
    jql = (
        f'project = {PROJECT} AND sprint not in openSprints() '
        f'AND status = "To Do" '
        f'AND "Epic Link" in ({epic_csv})'
    )
    fields = [
        "summary", "description", "status", "assignee", "parent",
        "issuetype", "customfield_10032",
        AC_FIELD,
        "labels", "priority",
    ]
    issues = jira_search(jql, fields)
    print(f"   Raw issues: {len(issues)}")

    tickets = []
    for issue in issues:
        f = issue["fields"]

        if f.get("issuetype", {}).get("name", "") in ("Epic", "Objective"):
            continue

        parent    = f.get("parent") or {}
        epic_key  = parent.get("key", "N/A")
        epic_name = (parent.get("fields") or {}).get("summary", "Unepic Work")

        sp_raw = f.get("customfield_10032")

        tickets.append({
            "key": issue["key"],
            "summary": f.get("summary", ""),
            "status": f.get("status", {}).get("name", "Unknown"),
            "assignee": (f.get("assignee") or {}).get("displayName", "Unassigned"),
            "epic_key": epic_key,
            "epic_name": epic_name,
            "description": parse_field(f.get("description"))[:1000],
            "ac": parse_field(f.get(AC_FIELD))[:1000],
            "story_points": int(sp_raw) if isinstance(sp_raw, (int, float)) else None,
            "labels": f.get("labels") or [],
        })

    output = {
        "fetched_at": now_iso(),
        "project": PROJECT,
        "epic_keys": EPIC_KEYS,
        "ac_field": AC_FIELD,
        "scope": "backlog",
        "ticket_count": len(tickets),
        "tickets": tickets,
    }

    out_path = OUTPUT_DIR / "backlog.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)

    print(f"✓ Written: {out_path}")
    print(f"  Backlog tickets: {len(tickets)}")


if __name__ == "__main__":
    main()
