#!/usr/bin/env python3
"""
fetch_confluence.py — Fetch current PIF Weekly Progress Confluence page and extract last week's data.

Outputs (in ./output/):
    current_page_storage.txt  — full page body in Confluence storage (XHTML) format
    current_version.txt       — current page version number (integer)
    last_week.json            — last week's table rows parsed from the most recent table entry
"""

import os
import sys
import json
import re
import requests
from base64 import b64encode

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL = os.environ.get("ATLASSIAN_BASE_URL", "https://kroger.atlassian.net")
EMAIL    = os.environ.get("ATLASSIAN_EMAIL", "")
TOKEN    = os.environ.get("ATLASSIAN_API_TOKEN", "")
PAGE_ID  = "514261050"
# ─────────────────────────────────────────────────────────────────────────────


def auth_header() -> dict:
    creds = b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
    return {"Authorization": f"Basic {creds}", "Content-Type": "application/json", "Accept": "application/json"}


def fetch_page() -> dict:
    url = f"{BASE_URL}/wiki/rest/api/content/{PAGE_ID}"
    resp = requests.get(url, headers=auth_header(), params={
        "expand": "body.storage,version",
    })
    resp.raise_for_status()
    return resp.json()


def strip_tags(html: str) -> str:
    """Remove XML/HTML tags from a string, collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def parse_last_week_table(storage_body: str) -> list[dict]:
    """
    Parse the first <table> in the page storage body.
    Returns a list of row dicts: {service, progress, next_steps, blockers}
    """
    # Find the first table
    table_match = re.search(r"<table\b[^>]*>(.*?)</table>", storage_body, re.DOTALL | re.IGNORECASE)
    if not table_match:
        return []

    table_html = table_match.group(1)

    # Extract all <tr> blocks
    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", table_html, re.DOTALL | re.IGNORECASE)
    result = []
    for row in rows:
        cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, re.DOTALL | re.IGNORECASE)
        texts = [strip_tags(c) for c in cells]
        if len(texts) >= 4 and texts[0].lower() not in ("service", ""):
            result.append({
                "service":    texts[0],
                "progress":   texts[1],
                "next_steps": texts[2],
                "blockers":   texts[3] if len(texts) > 3 else "",
            })
    return result


def main():
    if not EMAIL or not TOKEN:
        print("ERROR: ATLASSIAN_EMAIL and ATLASSIAN_API_TOKEN must be set.", file=sys.stderr)
        sys.exit(1)

    os.makedirs("output", exist_ok=True)

    print("→ Fetching Confluence page...")
    page = fetch_page()

    version = page["version"]["number"]
    storage_body = page["body"]["storage"]["value"]

    with open("output/current_page_storage.txt", "w", encoding="utf-8") as f:
        f.write(storage_body)
    with open("output/current_version.txt", "w") as f:
        f.write(str(version))

    print(f"   Page version: {version}")

    last_week = parse_last_week_table(storage_body)
    with open("output/last_week.json", "w", encoding="utf-8") as f:
        json.dump(last_week, f, indent=2, ensure_ascii=False)

    print(f"   Last week rows found: {len(last_week)}")
    for row in last_week:
        print(f"   - {row['service']}")

    print("✓ Written: output/current_page_storage.txt, output/current_version.txt, output/last_week.json")


if __name__ == "__main__":
    main()
