#!/usr/bin/env python3
"""
PIF Weekly Confluence update via Jira/Confluence REST API (basic auth),
used as a fallback when the Atlassian MCP connection is unavailable.

Mirrors weekly_update_prompt.md steps 1-4 (fetch) and 7-9 (assemble/publish).
Step 5-6 (synthesizing prose for each epic's Progress/Next Steps/Blockers
cells) is NOT done by this script — that requires judgment and is done by
Claude reading the fetched JSON, then written to output/new_section.json
before running this script with --publish.

Usage:
    python3 scripts/weekly_update_rest.py --fetch --week-start 2026-09-14 --week-end 2026-09-18 --sprint "DCP 2026Q3.3"
    # ... Claude writes output/new_section.json ...
    python3 scripts/weekly_update_rest.py --publish --week-start 2026-09-14 --week-end 2026-09-18 --sprint "DCP 2026Q3.3"

Credentials are read from .env in the project root: ATLASSIAN_EMAIL, ATLASSIAN_API_TOKEN,
ATLASSIAN_BASE_URL (defaults to https://kroger.atlassian.net).
"""
import argparse
import base64
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
ENV_FILE = PROJECT_ROOT / ".env"

CONFLUENCE_PAGE_ID = "514261050"
CONFLUENCE_SPACE = "apiprogram"
JIRA_PROJECT = "DCPFS"
PIF_TEAM_FIELD_ID = "18d9661f-511b-4e04-8bd8-cb82f16f27e0"


def load_env():
    env = dict(os.environ)
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip())
    return env


ENV = load_env()
EMAIL = ENV.get("ATLASSIAN_EMAIL")
TOKEN = ENV.get("ATLASSIAN_API_TOKEN")
BASE_URL = ENV.get("ATLASSIAN_BASE_URL", "https://kroger.atlassian.net").rstrip("/")

if not EMAIL or not TOKEN:
    sys.exit("ERROR: ATLASSIAN_EMAIL / ATLASSIAN_API_TOKEN not found in .env")

AUTH_HEADER = "Basic " + base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()


def api_get(path, params=None):
    url = f"{BASE_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": AUTH_HEADER, "Accept": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def api_put_json(path, payload):
    url = f"{BASE_URL}{path}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, method="PUT",
        headers={"Authorization": AUTH_HEADER, "Accept": "application/json", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def jql_search(jql, fields, max_results=100, expand=None):
    params = {"jql": jql, "fields": ",".join(fields), "maxResults": max_results}
    if expand:
        params["expand"] = expand
    return api_get("/rest/api/3/search/jql", params)


def html_to_text(fragment):
    if not fragment:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", fragment)
    text = re.sub(r"</p>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def step1_sprint_info(week_start, week_end, sprint_override):
    if sprint_override:
        quarter_label = sprint_override
    else:
        data = jql_search(
            "project = DCPFS AND sprint in openSprints() ORDER BY created ASC",
            ["customfield_10020"], max_results=1,
        )
        issues = data.get("issues", [])
        if not issues:
            sys.exit("ERROR: No active sprint found in DCPFS")
        sprints = issues[0]["fields"].get("customfield_10020") or []
        active = next((s for s in sprints if s.get("state") == "active"), None)
        if not active:
            sys.exit("ERROR: No active sprint found in DCPFS")
        quarter_label = active["name"]

    def ordinal(n):
        if 11 <= n % 100 <= 13:
            return f"{n}th"
        return f"{n}{ {1:'st',2:'nd',3:'rd'}.get(n % 10, 'th') }"

    def display(date_str):
        import datetime
        d = datetime.date.fromisoformat(date_str)
        return f"{ordinal(d.day)} {d.strftime('%B %Y')}"

    info = {
        "name": quarter_label,
        "week_start": week_start,
        "week_end": week_end,
        "week_start_display": display(week_start),
        "week_end_display": display(week_end),
    }
    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / "sprint_info.json").write_text(json.dumps(info, indent=2))
    print(f"→ [1/9] Sprint: {info['name']} | Week: {info['week_start_display']} - {info['week_end_display']}")
    return info


def step2_epics():
    jql = (
        f'project = {JIRA_PROJECT} AND issuetype = Epic AND status not in (Closed, Done) '
        f'AND "Team[Team]" = "{PIF_TEAM_FIELD_ID}"'
    )
    data = jql_search(jql, ["summary", "status", "key"], max_results=30)
    issues = data.get("issues", [])
    epic_keys = [i["key"] for i in issues]
    epic_names = {i["key"]: i["fields"]["summary"] for i in issues}
    if not epic_keys:
        sys.exit("ERROR: No PIF epics found")
    (OUTPUT_DIR / "epic_keys.json").write_text(json.dumps(epic_keys, indent=2))
    print(f"→ [2/9] PIF epics: {len(epic_keys)} keys — {', '.join(epic_keys)}")
    return epic_keys, epic_names


def step3_tickets(quarter_label, week_start, epic_keys):
    epic_list = ", ".join(epic_keys)
    jql = (
        f'project = {JIRA_PROJECT} AND sprint = "{quarter_label}" AND status != "To Do" '
        f'AND updated >= "{week_start}" AND "Epic Link" in ({epic_list})'
    )
    data = jql_search(
        jql, ["summary", "description", "status", "parent", "comment", "assignee", "issuetype"],
        max_results=100, expand="renderedFields",
    )
    issues = data.get("issues", [])
    fallback_used = False
    if not issues:
        fallback_used = True
        jql = (
            f'project = {JIRA_PROJECT} AND sprint = "{quarter_label}" AND status != "To Do" '
            f'AND "Epic Link" in ({epic_list})'
        )
        data = jql_search(
            jql, ["summary", "description", "status", "parent", "comment", "assignee", "issuetype"],
            max_results=100, expand="renderedFields",
        )
        issues = data.get("issues", [])

    tickets_by_epic = {}
    total = 0
    for issue in issues:
        f = issue["fields"]
        if f["issuetype"]["name"] in ("Epic", "Objective"):
            continue
        parent = f.get("parent")
        epic_name = parent["fields"]["summary"] if parent else "General / Unepic Work"
        epic_key = parent["key"] if parent else None

        rendered = issue.get("renderedFields", {})
        desc_html = rendered.get("description") or ""
        description = html_to_text(desc_html)[:400]

        comments_raw = rendered.get("comment", {}).get("comments", [])
        comments_raw_sorted = sorted(comments_raw, key=lambda c: c.get("created", ""), reverse=True)
        comments = [html_to_text(c.get("body", ""))[:200] for c in comments_raw_sorted[:3]]

        ticket = {
            "key": issue["key"],
            "summary": f["summary"],
            "status": f["status"]["name"],
            "assignee": (f.get("assignee") or {}).get("displayName", ""),
            "description": description,
            "comments": comments,
        }
        tickets_by_epic.setdefault(epic_name, {"epic_key": epic_key, "tickets": []})
        tickets_by_epic[epic_name]["tickets"].append(ticket)
        total += 1

    (OUTPUT_DIR / "tickets_by_epic.json").write_text(json.dumps(tickets_by_epic, indent=2))
    suffix = " (fallback: no date filter)" if fallback_used else ""
    print(f"→ [3/9] Tickets fetched: {total} across {len(tickets_by_epic)} epics{suffix}")
    return tickets_by_epic


def step4_confluence_page():
    data = api_get(f"/wiki/api/v2/pages/{CONFLUENCE_PAGE_ID}", {"body-format": "storage"})
    body = data["body"]["storage"]["value"]
    version = data["version"]["number"]
    (OUTPUT_DIR / "current_page_body.md").write_text(body)

    table_match = re.search(r"<table.*?</table>", body, re.DOTALL)
    last_week_rows = []
    service_names = []
    if table_match:
        table_html = table_match.group(0)
        row_matches = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL)
        for row_html in row_matches[1:]:  # skip header row
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
            if len(cells) < 4:
                continue
            service, progress, next_steps, blockers = [html_to_text(c) for c in cells[:4]]
            last_week_rows.append({
                "service": service, "progress": progress,
                "next_steps": next_steps, "blockers": blockers,
            })
            service_names.append(service)

    (OUTPUT_DIR / "last_week.json").write_text(json.dumps(last_week_rows, indent=2))
    (OUTPUT_DIR / "_page_version.json").write_text(json.dumps({"version": version}))
    print(f"→ [4/9] Confluence page fetched | Last week table: {len(last_week_rows)} epic rows parsed — {', '.join(service_names)}")
    return body, version, last_week_rows


def markdown_cell_to_storage(text):
    """Convert '<br>'-separated plain text lines into Confluence storage <p> paragraphs."""
    if not text:
        return '<p local-id=""/>'
    parts = re.split(r"\s*<br\s*/?>\s*", text)
    return "".join(f"<p>{html.escape(part)}</p>" for part in parts if part.strip())


def build_new_section_storage(section):
    rows_html = ""
    for row in section["rows"]:
        rows_html += (
            "<tr>"
            f"<td><p>{html.escape(row['service'])}</p></td>"
            f"<td>{markdown_cell_to_storage(row['progress'])}</td>"
            f"<td>{markdown_cell_to_storage(row['next_steps'])}</td>"
            f"<td>{markdown_cell_to_storage(row['blockers'])}</td>"
            "<td><p/></td>"
            "</tr>"
        )
    header = (
        "<tr><th><p>Service</p></th><th><p>Progress</p></th>"
        "<th><p>Next Steps</p></th><th><p>Blocker/ Targets</p></th><th><p/></th></tr>"
    )
    table = f'<table data-table-width="1800" data-layout="default"><tbody>{header}{rows_html}</tbody></table>'
    return (
        f"<h3>{html.escape(section['quarter_label'])}</h3>"
        f"<h3>{html.escape(section['week_range'])}</h3>"
        f"{table}"
        "<p>&zwnj;</p>"
    )


def step7_8_9(week_start, week_end, sprint_info, epic_keys, tickets_by_epic, dry_run=False):
    section_path = OUTPUT_DIR / "new_section.json"
    if not section_path.exists():
        sys.exit(f"ERROR: {section_path} not found. Run step 5/6 (synthesis) first and write this file.")
    section = json.loads(section_path.read_text())

    current_body = (OUTPUT_DIR / "current_page_body.md").read_text()
    version_info = json.loads((OUTPUT_DIR / "_page_version.json").read_text())
    current_version = version_info["version"]

    new_section_html = build_new_section_storage(section)
    new_body = new_section_html + current_body
    print(f"→ [7/9] Page body assembled (NEW_SECTION prepended to {len(current_body)} bytes of history)")

    if len(current_body) < 3000 or current_body.count("<h3") < 3:
        sys.exit("ERROR: Body truncation detected. Refusing to publish.")

    if dry_run:
        (OUTPUT_DIR / "_dry_run_body.html").write_text(new_body)
        print("→ [8/9] DRY RUN — not publishing. Body written to output/_dry_run_body.html")
        return

    payload = {
        "id": CONFLUENCE_PAGE_ID,
        "status": "current",
        "title": "PIF Weekly Progress 2026",
        "body": {"representation": "storage", "value": new_body},
        "version": {"number": current_version + 1, "message": "Automated weekly update (REST API fallback)"},
    }
    result = api_put_json(f"/wiki/api/v2/pages/{CONFLUENCE_PAGE_ID}", payload)
    new_version = result["version"]["number"]
    print(f"→ [8/9] Confluence page updated (body size: {len(new_body)} including all history)")

    tickets_read = sum(len(v["tickets"]) for v in tickets_by_epic.values())
    status = {
        "status": "complete",
        "page_id": CONFLUENCE_PAGE_ID,
        "page_version": new_version,
        "sprint": sprint_info["name"],
        "week_start": week_start,
        "week_end": week_end,
        "epics_covered": len(tickets_by_epic),
        "tickets_read": tickets_read,
    }
    (OUTPUT_DIR / "weekly_update_status.json").write_text(json.dumps(status, indent=2))
    print("✅ Done.")
    print(f"Sprint:          {sprint_info['name']}")
    print(f"Week:            {sprint_info['week_start_display']} - {sprint_info['week_end_display']}")
    print(f"Epics covered:   {len(tickets_by_epic)}")
    print(f"Tickets read:    {tickets_read}")
    print(f"URL: {BASE_URL}/wiki/spaces/{CONFLUENCE_SPACE}/pages/{CONFLUENCE_PAGE_ID}/PIF+Weekly+Progress+2026")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-start", required=True)
    parser.add_argument("--week-end", required=True)
    parser.add_argument("--sprint", default="")
    parser.add_argument("--fetch", action="store_true", help="Run steps 1-4 (fetch data)")
    parser.add_argument("--publish", action="store_true", help="Run steps 7-9 (assemble + publish); requires output/new_section.json")
    parser.add_argument("--dry-run", action="store_true", help="With --publish, build the body but do not call updateConfluencePage")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)

    if args.fetch:
        sprint_info = step1_sprint_info(args.week_start, args.week_end, args.sprint)
        epic_keys, epic_names = step2_epics()
        tickets_by_epic = step3_tickets(sprint_info["name"], args.week_start, epic_keys)
        step4_confluence_page()

    if args.publish:
        sprint_info = json.loads((OUTPUT_DIR / "sprint_info.json").read_text())
        tickets_by_epic = json.loads((OUTPUT_DIR / "tickets_by_epic.json").read_text())
        step7_8_9(args.week_start, args.week_end, sprint_info, None, tickets_by_epic, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
