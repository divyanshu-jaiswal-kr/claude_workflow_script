#!/usr/bin/env python3
"""
confluence_utils.py — Shared Confluence REST helper for PIF workflow scripts.

Provides:
  - Auth and HTTP helpers
  - get_page(), update_page(), create_page()
  - get_footer_comments()
  - XHTML storage format builders (xe, h1, h2, h3, p, hr, table, ul, link, strong, code_span)
"""

import os
import re
import sys
import requests
from base64 import b64encode
from datetime import datetime, timezone

# ── Config from environment ───────────────────────────────────────────────────
BASE_URL = os.environ.get("ATLASSIAN_BASE_URL", "https://kroger.atlassian.net")
EMAIL    = os.environ.get("ATLASSIAN_EMAIL", "")
TOKEN    = os.environ.get("ATLASSIAN_API_TOKEN", "")
# ─────────────────────────────────────────────────────────────────────────────


def check_env() -> None:
    """Exit with an error if Atlassian credentials are not set."""
    if not EMAIL or not TOKEN:
        print("ERROR: ATLASSIAN_EMAIL and ATLASSIAN_API_TOKEN must be set.", file=sys.stderr)
        sys.exit(1)


def auth_header() -> dict:
    """Return Basic auth header dict for Atlassian REST API calls."""
    creds = b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ── Page operations ───────────────────────────────────────────────────────────

def get_page(page_id: str) -> dict:
    """GET a Confluence page with storage body and version info."""
    url = f"{BASE_URL}/wiki/rest/api/content/{page_id}"
    resp = requests.get(url, headers=auth_header(), params={"expand": "body.storage,version,title"})
    resp.raise_for_status()
    return resp.json()


def get_page_version(page_id: str) -> int:
    """Return the current version number of a page."""
    page = get_page(page_id)
    return page["version"]["number"]


def update_page(page_id: str, title: str, body_storage: str, current_version: int) -> dict:
    """
    PUT to update a Confluence page with storage-format body.
    Handles 409 version conflicts by re-fetching the current version and retrying once.
    """
    url = f"{BASE_URL}/wiki/rest/api/content/{page_id}"
    payload = {
        "version": {"number": current_version + 1},
        "title": title,
        "type": "page",
        "body": {"storage": {"value": body_storage, "representation": "storage"}},
    }
    resp = requests.put(url, headers=auth_header(), json=payload)
    if resp.status_code == 409:
        # Version conflict — re-fetch and retry once
        new_ver = get_page_version(page_id)
        payload["version"]["number"] = new_ver + 1
        resp = requests.put(url, headers=auth_header(), json=payload)
    resp.raise_for_status()
    return resp.json()


def create_page(title: str, body_storage: str, space_key: str, parent_id: str) -> dict:
    """
    POST to create a new Confluence page with storage-format body.
    Returns the created page dict (includes 'id' and '_links').
    """
    url = f"{BASE_URL}/wiki/rest/api/content/"
    payload = {
        "type": "page",
        "title": title,
        "space": {"key": space_key},
        "ancestors": [{"id": str(parent_id)}],
        "body": {"storage": {"value": body_storage, "representation": "storage"}},
    }
    resp = requests.post(url, headers=auth_header(), json=payload)
    resp.raise_for_status()
    return resp.json()


def get_footer_comments(page_id: str) -> list[str]:
    """
    GET footer comments for a Confluence page.
    Returns a list of plain-text comment bodies (HTML stripped).
    """
    url = f"{BASE_URL}/wiki/rest/api/content/{page_id}/child/comment"
    resp = requests.get(url, headers=auth_header(), params={"expand": "body.storage", "limit": 25})
    resp.raise_for_status()
    results = resp.json().get("results", [])
    bodies = []
    for comment in results:
        raw = comment.get("body", {}).get("storage", {}).get("value", "")
        bodies.append(_strip_tags(raw).strip())
    return [b for b in bodies if b]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _strip_tags(html: str) -> str:
    """Remove all XML/HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


# ── XHTML storage format builders ─────────────────────────────────────────────

def xe(text: str) -> str:
    """Escape a string for inclusion in Confluence storage XML."""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def h1(text: str) -> str:
    return f"<h1>{xe(text)}</h1>"


def h2(text: str) -> str:
    return f"<h2>{xe(text)}</h2>"


def h3(text: str) -> str:
    return f"<h3>{xe(text)}</h3>"


def p(content: str) -> str:
    """Wrap content in a paragraph. content may contain already-escaped XML."""
    return f"<p>{content}</p>"


def hr() -> str:
    return "<hr/>"


def strong(text: str) -> str:
    return f"<strong>{xe(text)}</strong>"


def em(text: str) -> str:
    return f"<em>{xe(text)}</em>"


def code_span(text: str) -> str:
    return f"<code>{xe(text)}</code>"


def link(url: str, text: str) -> str:
    return f'<a href="{xe(url)}">{xe(text)}</a>'


def jira_link(key: str) -> str:
    """Return an XHTML link to a Jira issue."""
    url = f"{BASE_URL}/browse/{key}"
    return link(url, key)


def table(headers: list[str], rows: list[list[str]]) -> str:
    """
    Build a Confluence storage HTML table.
    headers: list of header strings (already xe-escaped or containing HTML)
    rows: list of row lists (each cell is a string, will be xe-escaped if plain text)
    Pass xe(value) or pre-built HTML for cells that need formatting.
    """
    th_cells = "".join(f"<th>{h}</th>" for h in headers)
    thead_row = f"<tr>{th_cells}</tr>"
    body_rows = []
    for row in rows:
        td_cells = "".join(f"<td>{cell}</td>" for cell in row)
        body_rows.append(f"<tr>{td_cells}</tr>")
    return "<table><tbody>" + thead_row + "".join(body_rows) + "</tbody></table>"


def ul(items: list[str]) -> str:
    """Build an unordered list. Items may contain pre-built HTML."""
    if not items:
        return "<p>(none)</p>"
    li_items = "".join(f"<li>{item}</li>" for item in items)
    return f"<ul>{li_items}</ul>"


def info_panel(content: str) -> str:
    """Confluence info panel macro (blue box)."""
    return (
        '<ac:structured-macro ac:name="info">'
        f"<ac:rich-text-body><p>{content}</p></ac:rich-text-body>"
        "</ac:structured-macro>"
    )


def now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def page_url(page_id: str, space_key: str = "apiprogram") -> str:
    """Return the Confluence page URL for a given page ID."""
    return f"{BASE_URL}/wiki/spaces/{space_key}/pages/{page_id}"
