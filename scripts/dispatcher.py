#!/usr/bin/env python3
"""
dispatcher.py — Parse PIF command page, write execution plan, reset page.

Replaces prompts/dispatcher.md — zero Claude tokens.

Steps:
  1. GET command page (storage format)
  2. Parse checked task items → commands list
  3. Parse "Additional Tasks" section → inline_tasks list
  4. GET footer comments → comment_tasks list
  5. Parse config values from page text
  6. Write state/execution_plan.json
  7. Reset: uncheck all, clear Additional Tasks bullets, update "Last run:"
  8. PUT updated page back
"""

import os
import re
import sys
import json
import requests
from datetime import datetime, timezone
from pathlib import Path

# Allow importing confluence_utils from the same directory
sys.path.insert(0, str(Path(__file__).parent))
from confluence_utils import (
    check_env, auth_header, get_page, update_page,
    get_footer_comments, _strip_tags, BASE_URL,
)

# ── Config from environment ───────────────────────────────────────────────────
COMMAND_PAGE_ID       = os.environ.get("COMMAND_PAGE_ID", "")
COMMAND_PAGE_PARENT_ID = os.environ.get("COMMAND_PAGE_PARENT_ID", "1112015485")

VALID_COMMANDS = {
    "weekly_progress", "sprint_summary", "board_report",
    "ticket_quality", "fix_descriptions", "fix_tickets",
    "browse_folder",
}

STATE_DIR = Path(__file__).parent.parent / "state"
# ─────────────────────────────────────────────────────────────────────────────


def parse_checked_commands(storage_body: str) -> list[str]:
    """
    Parse Confluence storage XML for checked task items.

    Confluence stores markdown `- [x] **name**` as:
      <ac:task-list>
        <ac:task>
          <ac:task-status>complete</ac:task-status>
          <ac:task-body><strong>name</strong> — description</ac:task-body>
        </ac:task>
      </ac:task-list>

    Falls back to searching for literal [x] in text content.
    """
    commands = []

    # ── Primary: Confluence native task list format ───────────────────────────
    task_pattern = re.compile(
        r"<ac:task>.*?<ac:task-status>(complete|incomplete)</ac:task-status>"
        r".*?<ac:task-body>(.*?)</ac:task-body>.*?</ac:task>",
        re.DOTALL | re.IGNORECASE,
    )
    for m in task_pattern.finditer(storage_body):
        status = m.group(1).strip().lower()
        body_text = _strip_tags(m.group(2))
        # Extract the first word as the command name (before " —" or space)
        cmd = re.split(r"[\s\-—]", body_text.strip())[0].strip().lower()
        if status == "complete" and cmd in VALID_COMMANDS:
            commands.append(cmd)

    if commands:
        return commands

    # ── Fallback: plain text [x] pattern ─────────────────────────────────────
    plain_text = _strip_tags(storage_body)
    for line in plain_text.splitlines():
        m = re.search(r"\[x\]\s+\*?\*?(\w+)", line, re.IGNORECASE)
        if m:
            cmd = m.group(1).lower()
            if cmd in VALID_COMMANDS:
                commands.append(cmd)

    return commands


def parse_config(storage_body: str) -> dict:
    """
    Extract configuration values from the command page storage body.
    Looks for patterns like:
      <strong>Ticket quality scope:</strong> <code>sprint</code>
    Also handles plain text versions as fallback.
    """
    plain = _strip_tags(storage_body)

    def extract_between(label_pattern: str, text: str):
        """Find label and grab backtick-quoted or word value after it."""
        m = re.search(label_pattern + r"[:\s]*`?([^`\n]+)`?", text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    # ticket_quality_scope
    scope_raw = extract_between(r"ticket quality scope", plain)
    scope = scope_raw if scope_raw in {"sprint", "backlog", "all"} else "sprint"

    # board_report_days
    days_raw = extract_between(r"board report.*?days back", plain)
    try:
        days = int(days_raw) if days_raw else 7
    except (ValueError, TypeError):
        days = 7

    # fix_descriptions_keys — comma-separated Jira keys
    keys_raw = extract_between(r"fix descriptions.*?ticket keys", plain)
    if keys_raw and "paste keys" in keys_raw.lower():
        keys_raw = ""
    fix_keys = keys_raw.strip() if keys_raw else ""

    # create_page_parent
    parent_raw = extract_between(r"create page.*?parent id", plain)
    create_parent = parent_raw if parent_raw else COMMAND_PAGE_PARENT_ID

    return {
        "ticket_quality_scope": scope,
        "board_report_days": days,
        "fix_descriptions_keys": fix_keys,
        "create_page_parent": str(create_parent).strip(),
    }


def parse_inline_tasks(storage_body: str) -> list[str]:
    """
    Extract tasks from the "Additional Tasks" section of the command page.

    In Confluence storage format, the section is stored as:
      <h2>Additional Tasks</h2>
      ...
      <ul><li>task text</li><li>another task</li></ul>
      <h2>Next Section</h2>

    Extracts <li> text between the Additional Tasks heading and the next
    heading (h2/h3). Also handles plain-text `- task` fallback.
    Skips empty items.
    """
    # ── Primary: extract <li> content from the section ───────────────────────
    # Isolate the HTML between the Additional Tasks heading and the next h2/h3
    section_match = re.search(
        r"Additional Tasks.*?(?=<h[123]|$)",
        storage_body,
        re.DOTALL | re.IGNORECASE,
    )
    if section_match:
        section_html = section_match.group(0)
        # Pull out all <li>...</li> text
        li_items = re.findall(r"<li[^>]*>(.*?)</li>", section_html, re.DOTALL | re.IGNORECASE)
        tasks = []
        for item in li_items:
            text = _strip_tags(item).strip()
            if text:
                tasks.append(text)
        if tasks:
            return tasks

    # ── Fallback: plain-text `- task` pattern ────────────────────────────────
    plain = _strip_tags(storage_body)
    section_match = re.search(
        r"Additional Tasks.*?(?=\n##|\Z)",
        plain,
        re.DOTALL | re.IGNORECASE,
    )
    if not section_match:
        return []

    tasks = []
    for line in section_match.group(0).splitlines():
        line = line.strip()
        m = re.match(r"^[-•]\s+(.+)", line)
        if m:
            text = m.group(1).strip()
            if text:
                tasks.append(text)
    return tasks


def clear_inline_tasks(storage_body: str) -> str:
    """
    Clear all bullet items in the Additional Tasks section, leaving just the
    empty placeholder bullet `- ` so users know where to write next time.

    Works by finding the section in storage XHTML and replacing list item
    content, with a plain-text fallback using regex on the raw storage string.
    """
    # Strategy: find <ul> blocks that come after the "Additional Tasks" heading
    # and replace all <li> content with a single empty <li></li>.
    # Confluence stores the section as: <h2>Additional Tasks</h2>...<ul>...</ul>
    pattern = re.compile(
        r"(Additional Tasks.*?<ul[^>]*>).*?(</ul>)",
        re.DOTALL | re.IGNORECASE,
    )
    replaced = pattern.sub(r"\1<li></li>\2", storage_body)
    if replaced != storage_body:
        return replaced

    # Fallback: leave the body unchanged (tasks will persist but won't re-run
    # because they're only read once per dispatch cycle)
    return storage_body


def reset_page_body(storage_body: str) -> str:
    """
    Return an updated storage body with:
    1. All <ac:task-status>complete</ac:task-status> → incomplete
    2. Additional Tasks section bullets cleared
    3. Last-run timestamp updated
    """
    # Uncheck all tasks
    updated = re.sub(
        r"<ac:task-status>complete</ac:task-status>",
        "<ac:task-status>incomplete</ac:task-status>",
        storage_body,
        flags=re.IGNORECASE,
    )

    # Clear Additional Tasks bullets
    updated = clear_inline_tasks(updated)

    # Update "Last run:" text — it may be in a blockquote paragraph
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M ET")
    updated = re.sub(
        r"(<strong>Last run:</strong>\s*)([^<]*)",
        rf"\g<1>{now_str}",
        updated,
        flags=re.IGNORECASE,
    )
    # Fallback: plain text pattern (if not wrapped in strong tags)
    if "Last run:" in updated and now_str not in updated:
        updated = re.sub(
            r"(Last run:\s*)([^\n<]*)",
            rf"\g<1>{now_str}",
            updated,
            flags=re.IGNORECASE,
        )

    return updated


def main() -> None:
    check_env()

    if not COMMAND_PAGE_ID:
        print("ERROR: COMMAND_PAGE_ID is not set. Run --setup first.", file=sys.stderr)
        sys.exit(1)

    STATE_DIR.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Fetch command page ────────────────────────────────────────────
    print(f"→ [Dispatcher] Fetching command page {COMMAND_PAGE_ID}...")
    try:
        page = get_page(COMMAND_PAGE_ID)
    except requests.HTTPError as e:
        print(f"ERROR: Could not fetch command page: {e}", file=sys.stderr)
        sys.exit(1)

    page_title   = page.get("title", "PIF Automation Commands")
    storage_body = page["body"]["storage"]["value"]
    version      = page["version"]["number"]
    print("→ [Dispatcher] Command page fetched.")

    # ── Step 2: Parse checked commands ───────────────────────────────────────
    commands = parse_checked_commands(storage_body)
    cmd_display = ", ".join(commands) if commands else "none"
    print(f"→ [Dispatcher] Checked commands: {cmd_display}")

    # ── Step 3: Parse inline tasks from "Additional Tasks" section ───────────
    inline_tasks = parse_inline_tasks(storage_body)
    if inline_tasks:
        print(f"→ [Dispatcher] Inline tasks from page: {len(inline_tasks)}")
        for t in inline_tasks:
            print(f"     • {t[:80]}")

    # ── Step 4: Get footer comments → additional custom tasks ─────────────────
    try:
        comment_bodies = get_footer_comments(COMMAND_PAGE_ID)
    except Exception as e:
        print(f"  ⚠  Could not fetch footer comments: {e}")
        comment_bodies = []

    # Combine inline tasks + comment tasks, deduplicating by text
    seen: set[str] = set()
    custom_tasks: list[dict] = []
    task_id = 1
    for text in inline_tasks:
        if text not in seen:
            custom_tasks.append({"id": task_id, "instruction": text, "source": "page"})
            seen.add(text)
            task_id += 1
    for body in comment_bodies:
        if body and body not in seen:
            custom_tasks.append({"id": task_id, "instruction": body, "source": "comment"})
            seen.add(body)
            task_id += 1

    if custom_tasks:
        print(f"→ [Dispatcher] Custom tasks total: {len(custom_tasks)} ({len(inline_tasks)} from page, {len(comment_bodies)} from comments)")

    # ── Step 5: Parse config ──────────────────────────────────────────────────
    config = parse_config(storage_body)
    print(
        f"→ [Dispatcher] Config: scope={config['ticket_quality_scope']} | "
        f"days={config['board_report_days']} | "
        f"fix_keys={config['fix_descriptions_keys'] or '(none)'}"
    )

    # ── Step 6: Write execution plan ──────────────────────────────────────────
    plan = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commands": commands,
        "custom_tasks": custom_tasks,
        "config": config,
    }
    plan_path = STATE_DIR / "execution_plan.json"
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    print(f"→ [Dispatcher] Execution plan written to {plan_path}")

    # ── Step 7: Reset page ────────────────────────────────────────────────────
    updated_body = reset_page_body(storage_body)
    try:
        update_page(COMMAND_PAGE_ID, page_title, updated_body, version)
        print("→ [Dispatcher] Command page reset. Last run timestamp updated.")
    except requests.HTTPError as e:
        print(f"  ⚠  Page reset failed (plan was written): {e}")

    # ── Step 8: Summary ───────────────────────────────────────────────────────
    if commands or custom_tasks:
        all_items = commands + [f"custom_task({t['id']})" for t in custom_tasks]
        print(f"\n✅ [Dispatcher] Done.")
        print(f"   Commands queued: {len(commands)} — {', '.join(commands) or 'none'}")
        if custom_tasks:
            print(f"   Custom tasks:   {len(custom_tasks)}")
        print(f"   Execution plan: {plan_path}")
    else:
        print("\nℹ️  [Dispatcher] No commands checked on the command page. Nothing to run.")


if __name__ == "__main__":
    main()
