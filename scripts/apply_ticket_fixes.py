#!/usr/bin/env python3
"""
apply_ticket_fixes.py — Apply AI-generated description and AC fixes to Jira tickets.

Reads:  output/ticket_fixes.json  (Claude's output from fix_tickets.md)
Action: REST PATCH each Jira issue with improved_description and/or improved_ac
No Claude — zero AI tokens.
"""

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from confluence_utils import check_env, auth_header, BASE_URL

import requests

# ── Config from environment ───────────────────────────────────────────────────
AC_FIELD   = os.environ.get("AC_FIELD", "customfield_10147")
OUTPUT_DIR = Path(__file__).parent.parent / "output"
# ─────────────────────────────────────────────────────────────────────────────


def text_to_adf(text: str) -> dict:
    """Convert a plain-text string to minimal ADF (paragraph node)."""
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


def update_issue(key: str, fields: dict) -> None:
    """PATCH a Jira issue with the given fields."""
    url = f"{BASE_URL}/rest/api/3/issue/{key}"
    payload = {"fields": fields}
    resp = requests.put(url, headers=auth_header(), json=payload)
    resp.raise_for_status()


def main() -> None:
    check_env()

    data_path = OUTPUT_DIR / "ticket_fixes.json"
    if not data_path.exists():
        print(f"ERROR: {data_path} not found. Run Claude fix_tickets.md first.", file=sys.stderr)
        sys.exit(1)

    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    fixes = data.get("fixes", [])
    if not fixes:
        print("ℹ️  No fixes to apply.")
        sys.exit(0)

    print(f"→ Applying fixes to {len(fixes)} tickets...")

    success = 0
    failed = []
    for fix in fixes:
        key  = fix.get("key", "")
        desc = fix.get("improved_description", "").strip()
        ac   = fix.get("improved_ac", "").strip()

        if not key:
            print("  ⚠  Skipping fix with no key.")
            continue

        fields_to_update: dict = {}
        if desc:
            fields_to_update["description"] = text_to_adf(desc)
        if ac:
            fields_to_update[AC_FIELD] = ac  # AC is stored as plain text

        if not fields_to_update:
            print(f"  ⚠  {key}: no fields to update (both description and AC are empty).")
            continue

        try:
            update_issue(key, fields_to_update)
            updated_fields = list(fields_to_update.keys())
            print(f"  ✅ {key}: updated {', '.join(updated_fields)}")
            success += 1
        except requests.HTTPError as e:
            print(f"  ❌ {key}: FAILED — {e}")
            failed.append(key)

    print(f"\n→ Done. {success}/{len(fixes)} tickets updated.")
    if failed:
        print(f"   Failed: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
