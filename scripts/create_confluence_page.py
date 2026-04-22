#!/usr/bin/env python3
"""
create_confluence_page.py — Standalone action script to create a Confluence page.

Usage:
  python3 create_confluence_page.py --title "Page Title" --body-file /path/to/body.html \
    [--parent-id 1112015485] [--space-key apiprogram]

The body file should contain Confluence storage XHTML.
For use by custom_task.md Claude output when a page needs to be created.
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from confluence_utils import check_env, create_page, page_url

# ── Defaults from environment ─────────────────────────────────────────────────
DEFAULT_SPACE  = os.environ.get("SPACE", "apiprogram")
DEFAULT_PARENT = os.environ.get("COMMAND_PAGE_PARENT_ID", "1112015485")
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a Confluence page from a storage XHTML file.")
    parser.add_argument("--title",      required=True, help="Page title")
    parser.add_argument("--body-file",  required=True, help="Path to XHTML storage body file")
    parser.add_argument("--parent-id",  default=DEFAULT_PARENT, help="Parent page ID")
    parser.add_argument("--space-key",  default=DEFAULT_SPACE,  help="Confluence space key")
    args = parser.parse_args()

    check_env()

    body_path = Path(args.body_file)
    if not body_path.exists():
        print(f"ERROR: Body file not found: {body_path}", file=sys.stderr)
        sys.exit(1)

    with open(body_path, encoding="utf-8") as f:
        body = f.read()

    print(f"→ Creating page: {args.title!r}")
    result = create_page(args.title, body, args.space_key, args.parent_id)
    page_id = result["id"]

    print(f"✅ Page created.")
    print(f"   Title:  {args.title}")
    print(f"   ID:     {page_id}")
    print(f"   URL:    {page_url(page_id, args.space_key)}")


if __name__ == "__main__":
    main()
