#!/usr/bin/env python3
"""
fetch_jira.py — Pull PIF team sprint data and tickets from Jira REST API.

Outputs (in ./output/):
    sprint_info.json      — sprint name, display dates, week range
    tickets_by_epic.json  — tickets grouped by parent epic, with comments
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime
from base64 import b64encode

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL = os.environ.get("ATLASSIAN_BASE_URL", "https://kroger.atlassian.net")
EMAIL    = os.environ.get("ATLASSIAN_EMAIL", "")
TOKEN    = os.environ.get("ATLASSIAN_API_TOKEN", "")
PROJECT  = "DCPFS"

# Known PIF epic keys — update this list at the start of each quarter.
# These are a fallback because Jira text search misses epics with underscores
# in their names (e.g. "Catalog V2_Q1 ...").
PIF_EPIC_KEYS_FALLBACK = [
    "DCPFS-27809",  # Catalog V2_Q1 Iterative tech enhancements
    "DCPFS-27807",  # Working PoC for Catalog bulk data delivery
    "DCPFS-27772",  # APIPIF Support Q1 2026
    "DCPFS-27778",  # APIPF Q1 2026 Ops/ Maintenance
]
# ─────────────────────────────────────────────────────────────────────────────


def auth_header() -> dict:
    creds = b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
    return {"Authorization": f"Basic {creds}", "Content-Type": "application/json", "Accept": "application/json"}


def jira_search(jql: str, fields: list[str], max_results: int = 100) -> list:
    """Paginated Jira issue search."""
    url = f"{BASE_URL}/rest/api/3/search"
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


def get_active_sprint() -> dict:
    """Return the active sprint object from customfield_10020."""
    issues = jira_search(
        jql=f"project = {PROJECT} AND sprint in openSprints()",
        fields=["customfield_10020"],
        max_results=1,
    )
    if not issues:
        raise RuntimeError("No open sprint found in DCPFS project.")
    for sprint in issues[0]["fields"].get("customfield_10020", []):
        if sprint.get("state") == "active":
            return sprint
    raise RuntimeError("No active sprint found.")


def discover_pif_epics() -> list[str]:
    """Discover PIF epics by name pattern, merged with the known fallback list."""
    issues = jira_search(
        jql=(
            f'project = {PROJECT} AND issuetype = Epic '
            f'AND status not in (Closed, Done) '
            f'AND (summary ~ "APIPIF" OR summary ~ "APIPF" '
            f'OR summary ~ "Catalog V2" OR summary ~ "bulk data" OR summary ~ "Catalog bulk")'
        ),
        fields=["summary", "status"],
    )
    discovered = {i["key"] for i in issues}
    all_keys = list(discovered | set(PIF_EPIC_KEYS_FALLBACK))
    return all_keys


def extract_adf_text(node) -> str:
    """Recursively extract plain text from an ADF (Atlassian Document Format) node."""
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    return " ".join(filter(None, (extract_adf_text(c) for c in node.get("content", []))))


def parse_field_text(field) -> str:
    """Parse a Jira field value that may be ADF, plain text, or null."""
    if field is None:
        return ""
    if isinstance(field, dict):
        return extract_adf_text(field)
    return str(field)


def latest_comments(comments: list, n: int = 3) -> list[str]:
    """Return the plain-text body of the N most recent comments."""
    return [parse_field_text(c.get("body", ""))[:300] for c in comments[-n:]][::-1]


def fetch_pif_tickets(epic_keys: list[str], week_start: str) -> list:
    """Fetch non-Todo PIF tickets updated since week_start; falls back without date filter."""
    epic_csv = ", ".join(epic_keys)
    base_jql = (
        f'project = {PROJECT} AND sprint in openSprints() '
        f'AND status != "To Do" '
        f'AND "Epic Link" in ({epic_csv})'
    )
    date_jql = base_jql + f' AND updated >= "{week_start}"'
    fields = ["summary", "description", "status", "parent", "comment", "assignee", "issuetype"]

    issues = jira_search(date_jql, fields)
    if not issues:
        print(f"  ⚠  No tickets updated since {week_start} — falling back to full sprint query.")
        issues = jira_search(base_jql, fields)
    return issues


def group_by_epic(issues: list) -> dict:
    """Group issue list into {epic_name: {epic_key, tickets[]}} dict."""
    grouped = {}
    for issue in issues:
        if issue["fields"]["issuetype"]["name"] in ("Epic", "Objective"):
            continue
        parent = issue["fields"].get("parent")
        epic_name = parent["fields"]["summary"] if parent else "General / Unepic Work"
        epic_key  = parent["key"]              if parent else "N/A"

        grouped.setdefault(epic_name, {"epic_key": epic_key, "tickets": []})

        comments_raw = issue["fields"].get("comment", {}).get("comments", [])
        grouped[epic_name]["tickets"].append({
            "key":         issue["key"],
            "summary":     issue["fields"]["summary"],
            "status":      issue["fields"]["status"]["name"],
            "assignee":    (issue["fields"].get("assignee") or {}).get("displayName", "Unassigned"),
            "description": parse_field_text(issue["fields"].get("description"))[:500],
            "comments":    latest_comments(comments_raw),
        })
    return grouped


def ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def display_date(date_str: str) -> str:
    """'2026-04-13' → '13th April 2026'"""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{ordinal(d.day)} {d.strftime('%B %Y')}"


def main():
    parser = argparse.ArgumentParser(description="Fetch PIF Jira sprint data.")
    parser.add_argument("--week-start", required=True, help="Start date YYYY-MM-DD (last Monday)")
    parser.add_argument("--week-end",   required=True, help="End date YYYY-MM-DD (today)")
    args = parser.parse_args()

    if not EMAIL or not TOKEN:
        print("ERROR: ATLASSIAN_EMAIL and ATLASSIAN_API_TOKEN must be set.", file=sys.stderr)
        sys.exit(1)

    os.makedirs("output", exist_ok=True)

    print("→ Fetching active sprint...")
    sprint = get_active_sprint()
    sprint_info = {
        "name":              sprint["name"],
        "week_start":        args.week_start,
        "week_end":          args.week_end,
        "week_start_display": display_date(args.week_start),
        "week_end_display":   display_date(args.week_end),
    }
    with open("output/sprint_info.json", "w") as f:
        json.dump(sprint_info, f, indent=2)
    print(f"   Sprint: {sprint_info['name']}  |  {sprint_info['week_start_display']} → {sprint_info['week_end_display']}")

    print("→ Discovering PIF epics...")
    epic_keys = discover_pif_epics()
    print(f"   Epics: {epic_keys}")

    print(f"→ Fetching tickets updated since {args.week_start}...")
    issues = fetch_pif_tickets(epic_keys, args.week_start)
    print(f"   Tickets: {len(issues)}")

    grouped = group_by_epic(issues)
    with open("output/tickets_by_epic.json", "w") as f:
        json.dump(grouped, f, indent=2, ensure_ascii=False)

    print("✓ Written: output/sprint_info.json, output/tickets_by_epic.json")


if __name__ == "__main__":
    main()
