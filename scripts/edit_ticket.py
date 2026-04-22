#!/usr/bin/env python3
"""
edit_ticket.py — Standalone action script to update a single Jira ticket field.

Usage:
  python3 edit_ticket.py --key DCPFS-12345 --field description --value "New description text"
  python3 edit_ticket.py --key DCPFS-12345 --field ac --value "AC line 1\nAC line 2"

Fields:
  description  — updates the Jira description field (converted to ADF)
  ac           — updates the AC custom field (customfield_10147, stored as plain text)
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from confluence_utils import check_env, auth_header, BASE_URL

import requests

# ── Config from environment ───────────────────────────────────────────────────
AC_FIELD = os.environ.get("AC_FIELD", "customfield_10147")
# ─────────────────────────────────────────────────────────────────────────────


def text_to_adf(text: str) -> dict:
    """Convert plain text to minimal ADF doc with paragraph nodes."""
    paragraphs = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line:
            paragraphs.append({
                "type": "paragraph",
                "content": [{"type": "text", "text": line}],
            })
    if not paragraphs:
        paragraphs = [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]
    return {"type": "doc", "version": 1, "content": paragraphs}


def main() -> None:
    parser = argparse.ArgumentParser(description="Update a single Jira ticket field.")
    parser.add_argument("--key",   required=True, help="Jira issue key, e.g. DCPFS-12345")
    parser.add_argument("--field", required=True, choices=["description", "ac"],
                        help="Field to update: description or ac")
    parser.add_argument("--value", required=True, help="New field value (plain text)")
    args = parser.parse_args()

    check_env()

    if args.field == "description":
        fields = {"description": text_to_adf(args.value)}
    else:  # ac
        fields = {AC_FIELD: args.value}

    url = f"{BASE_URL}/rest/api/3/issue/{args.key}"
    print(f"→ Updating {args.key} field '{args.field}'...")

    resp = requests.put(url, headers=auth_header(), json={"fields": fields})
    if resp.status_code == 204:
        print(f"✅ {args.key}: {args.field} updated successfully.")
    else:
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            print(f"❌ {args.key}: Update failed — {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
