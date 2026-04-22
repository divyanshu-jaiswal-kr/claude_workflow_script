#!/usr/bin/env python3
"""
update_confluence.py — Prepend the synthesized weekly section to the PIF Confluence page.

Reads (from ./output/):
    new_section.json          — synthesized table rows from Claude
    current_page_storage.txt  — existing page body (Confluence storage format)
    current_version.txt       — current page version number

Publishes:
    Updates Confluence page 514261050 with the new section prepended.
"""

import os
import sys
import json
import requests
from base64 import b64encode

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL   = os.environ.get("ATLASSIAN_BASE_URL", "https://kroger.atlassian.net")
EMAIL      = os.environ.get("ATLASSIAN_EMAIL", "")
TOKEN      = os.environ.get("ATLASSIAN_API_TOKEN", "")
PAGE_ID    = "514261050"
PAGE_TITLE = "PIF Weekly Progress 2026"
# ─────────────────────────────────────────────────────────────────────────────

ZWSP = "\u200c"  # zero-width non-joiner — used as paragraph separator in existing page format


def auth_header() -> dict:
    creds = b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
    return {"Authorization": f"Basic {creds}", "Content-Type": "application/json", "Accept": "application/json"}


def escape_xml(text: str) -> str:
    """Escape characters that are invalid in Confluence storage XML."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def build_storage_section(new_section: dict) -> str:
    """
    Convert new_section dict into Confluence storage (XHTML) format.

    Expected new_section keys:
        quarter_label  — e.g. "DCP 2026Q1.6"
        week_range     — e.g. "13th April 2026 - 19th April 2026"
        rows           — list of {service, progress, next_steps, blockers}
    """
    quarter_label = escape_xml(new_section.get("quarter_label", ""))
    week_range    = escape_xml(new_section.get("week_range", ""))
    rows          = new_section.get("rows", [])

    # Header
    lines = [
        f"<h3>{quarter_label}</h3>",
        f"<h3>{week_range}</h3>",
        "<table>",
        "  <tbody>",
        "    <tr>",
        "      <th>Service</th>",
        "      <th>Progress</th>",
        "      <th>Next Steps</th>",
        "      <th>Blocker/ Targets</th>",
        "      <th></th>",
        "    </tr>",
    ]

    for row in rows:
        service    = escape_xml(row.get("service", ""))
        progress   = escape_xml(row.get("progress", ""))
        next_steps = escape_xml(row.get("next_steps", ""))
        blockers   = escape_xml(row.get("blockers", ""))
        lines += [
            "    <tr>",
            f"      <td>{service}</td>",
            f"      <td>{progress}</td>",
            f"      <td>{next_steps}</td>",
            f"      <td>{blockers}</td>",
            "      <td></td>",
            "    </tr>",
        ]

    lines += [
        "  </tbody>",
        "</table>",
        f"<p>{ZWSP}</p>",
        "<p></p>",
    ]

    return "\n".join(lines)


def update_page(new_body: str, version: int, retried: bool = False) -> None:
    url = f"{BASE_URL}/wiki/rest/api/content/{PAGE_ID}"
    payload = {
        "version": {"number": version + 1},
        "title":   PAGE_TITLE,
        "type":    "page",
        "body": {
            "storage": {
                "value":          new_body,
                "representation": "storage",
            }
        },
    }
    resp = requests.put(url, headers=auth_header(), json=payload)

    if resp.status_code == 409 and not retried:
        # Version conflict — re-fetch current version and retry once
        print("  ⚠  Version conflict — re-fetching page version and retrying...")
        current = requests.get(url, headers=auth_header(), params={"expand": "version"})
        current.raise_for_status()
        new_version = current.json()["version"]["number"]
        update_page(new_body, new_version, retried=True)
        return

    resp.raise_for_status()


def main():
    if not EMAIL or not TOKEN:
        print("ERROR: ATLASSIAN_EMAIL and ATLASSIAN_API_TOKEN must be set.", file=sys.stderr)
        sys.exit(1)

    # ── Read outputs from previous steps ─────────────────────────────────────
    for path in ("output/new_section.json", "output/current_page_storage.txt", "output/current_version.txt"):
        if not os.path.exists(path):
            print(f"ERROR: Required file not found: {path}", file=sys.stderr)
            sys.exit(1)

    with open("output/new_section.json", encoding="utf-8") as f:
        new_section = json.load(f)

    with open("output/current_page_storage.txt", encoding="utf-8") as f:
        existing_body = f.read()

    with open("output/current_version.txt") as f:
        version = int(f.read().strip())

    # ── Build and prepend ─────────────────────────────────────────────────────
    print("→ Building new Confluence section...")
    new_storage_section = build_storage_section(new_section)

    updated_body = new_storage_section + "\n" + existing_body

    # ── Publish ───────────────────────────────────────────────────────────────
    print(f"→ Updating Confluence page (current version: {version})...")
    update_page(updated_body, version)

    rows = new_section.get("rows", [])
    print(f"✅ Confluence page updated successfully.")
    print(f"   Sprint: {new_section.get('quarter_label', '?')}")
    print(f"   Week:   {new_section.get('week_range', '?')}")
    print(f"   Epics summarized: {len(rows)}")
    print(f"   URL: {BASE_URL}/wiki/spaces/apiprogram/pages/{PAGE_ID}/PIF+Weekly+Progress+2026")


if __name__ == "__main__":
    main()
