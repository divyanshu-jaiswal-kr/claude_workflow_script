#!/usr/bin/env python3
"""
teams_bot.py — PIF PM Assistant bot for Microsoft Teams.

Architecture:
  - Teams Outgoing Webhook → POST /webhook  (Teams sends PM's message here)
  - Flask responds within 5s: "⏳ On it..."
  - Background thread runs Claude with the instruction
  - Result sent back to the Teams channel via Incoming Webhook URL
  - Short answers → Teams message directly
  - Long answers → Confluence page created + link posted to Teams

Setup (one-time):
  1. In Teams channel → ··· → Connectors → Incoming Webhook
     Name it "PIF Bot", copy URL → TEAMS_INCOMING_WEBHOOK_URL in config.sh
  2. In Teams → Apps → Outgoing Webhooks (team settings)
     Name: PIF Bot | Callback URL: http://<your-ip>:<PORT>/webhook
     Copy the HMAC secret → TEAMS_WEBHOOK_SECRET in config.sh
  3. (Recommended) Use ngrok for a public URL:
     ngrok http 3978   → use the https URL as the callback

Run:
  ./run_command.sh --teams
  (or) python3 scripts/teams_bot.py
"""

import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

# ── Flask ──────────────────────────────────────────────────────────────────────
try:
    from flask import Flask, jsonify, request
except ImportError:
    print("ERROR: Flask not installed. Run: pip3 install flask", file=sys.stderr)
    sys.exit(1)

try:
    import requests as _requests
except ImportError:
    print("ERROR: requests not installed. Run: pip3 install requests", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent))

# ── Config from environment ───────────────────────────────────────────────────
INCOMING_WEBHOOK_URL = os.environ.get("TEAMS_INCOMING_WEBHOOK_URL", "")
WEBHOOK_SECRET       = os.environ.get("TEAMS_WEBHOOK_SECRET", "")
PORT                 = int(os.environ.get("TEAMS_BOT_PORT", "3978"))
SCRIPT_DIR           = Path(__file__).parent.parent
CLAUDE_BIN           = os.environ.get("CLAUDE_BIN", "claude")

# Config forwarded to Claude prompt substitutions
SPACE_ID             = os.environ.get("SPACE_ID", "112984070")
SPACE                = os.environ.get("SPACE", "apiprogram")
EPIC_KEYS            = os.environ.get("EPIC_KEYS", "DCPFS-27809,DCPFS-27807,DCPFS-27772,DCPFS-27778")
COMMAND_PAGE_ID      = os.environ.get("COMMAND_PAGE_ID", "")
COMMAND_PAGE_PARENT  = os.environ.get("COMMAND_PAGE_PARENT_ID", "1112015485")
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)


# ── HMAC verification ─────────────────────────────────────────────────────────

def verify_teams_hmac(body: bytes, auth_header: str) -> bool:
    """
    Verify Teams Outgoing Webhook HMAC-SHA256 signature.
    Teams sends: Authorization: HMAC <base64-hmac>
    """
    if not WEBHOOK_SECRET:
        return True  # dev mode — skip verification if secret not configured
    if not auth_header or not auth_header.startswith("HMAC "):
        return False
    try:
        key = base64.b64decode(WEBHOOK_SECRET)
        expected = base64.b64encode(
            hmac.new(key, body, hashlib.sha256).digest()
        ).decode()
        received = auth_header[5:]  # strip "HMAC "
        return hmac.compare_digest(expected, received)
    except Exception:
        return False


# ── Teams message sender ──────────────────────────────────────────────────────

def send_to_teams(text: str, confluence_url: str = "", page_title: str = "") -> None:
    """
    POST a message to the Teams channel via Incoming Webhook.
    If confluence_url is set, adds an action button linking to it.
    """
    if not INCOMING_WEBHOOK_URL:
        print(f"\n[Teams →] {text}")
        if confluence_url:
            print(f"[Teams →] Link: {confluence_url}")
        return

    if confluence_url:
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "0078D4",
            "summary": page_title or text[:80],
            "sections": [{"text": text}],
            "potentialAction": [{
                "@type": "OpenUri",
                "name": f"📄 {page_title or 'View in Confluence'}",
                "targets": [{"os": "default", "uri": confluence_url}],
            }],
        }
    else:
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "0078D4",
            "text": text,
        }

    try:
        resp = _requests.post(INCOMING_WEBHOOK_URL, json=card, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"[Teams] Failed to send message: {e}")


# ── Data context builder ──────────────────────────────────────────────────────

def build_available_data() -> str:
    """List output/*.json files that already exist with their fetch times."""
    output_dir = SCRIPT_DIR / "output"
    DATA_FILES = {
        "sprint.json":  "Sprint ticket list (status, assignee, epic, story points)",
        "board.json":   "Sprint tickets with full description, AC, and all comments",
        "backlog.json": "Backlog (To Do) tickets with description and AC",
    }
    lines = []
    for fname, desc in DATA_FILES.items():
        fpath = output_dir / fname
        if fpath.exists():
            mtime = datetime.fromtimestamp(fpath.stat().st_mtime).strftime("%H:%M")
            lines.append(f"- `output/{fname}` — {desc} _(fetched {mtime})_")
    return "\n".join(lines) if lines else "_No output files yet. Use MCP or run a fetch script._"


# ── Claude runner ─────────────────────────────────────────────────────────────

def run_claude_task(instruction: str, sender: str) -> None:
    """
    Run Claude with the Teams instruction, parse its JSON output,
    and send the result back to Teams. Called in a background thread.
    """
    prompt_path = SCRIPT_DIR / "prompts" / "teams_task.md"
    if not prompt_path.exists():
        send_to_teams(f"❌ Missing prompts/teams_task.md")
        return

    template = prompt_path.read_text()

    subs = {
        "SPACE_ID_PLACEHOLDER":               SPACE_ID,
        "SPACE_PLACEHOLDER":                  SPACE,
        "EPIC_KEYS_PLACEHOLDER":              EPIC_KEYS,
        "COMMAND_PAGE_ID_PLACEHOLDER":        COMMAND_PAGE_ID,
        "COMMAND_PAGE_PARENT_ID_PLACEHOLDER": COMMAND_PAGE_PARENT,
        "AVAILABLE_DATA_PLACEHOLDER":         build_available_data(),
        "CUSTOM_INSTRUCTION_PLACEHOLDER":     instruction,
        "SENDER_PLACEHOLDER":                 sender,
    }

    body = template
    for k, v in subs.items():
        body = body.replace(k, v)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, dir="/tmp") as f:
        f.write(body)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [CLAUDE_BIN, "--dangerously-skip-permissions", "-p", open(tmp_path).read()],
            capture_output=True,
            text=True,
            timeout=120,
        )
        raw = result.stdout.strip()
        parsed = parse_claude_json(raw)

        answer        = parsed.get("answer", raw[:500] if raw else "No response.")
        confluence_url = parsed.get("confluence_url", "")
        page_title    = parsed.get("page_title", "")

        if result.returncode != 0 and not answer:
            send_to_teams(f"⚠️ Task completed with warnings.\n{raw[:400]}")
        else:
            send_to_teams(answer, confluence_url=confluence_url, page_title=page_title)

    except subprocess.TimeoutExpired:
        send_to_teams("⏱️ Request timed out after 2 minutes. Try a simpler query.")
    except Exception as e:
        send_to_teams(f"❌ Error: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def parse_claude_json(output: str) -> dict:
    """
    Extract JSON from Claude's response.
    Claude is instructed to output a JSON block — parse it.
    Falls back to treating the whole output as the answer.
    """
    # Try fenced JSON block first
    m = re.search(r"```json\s*(\{.*?\})\s*```", output, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Try raw JSON object
    m = re.search(r"\{[^{}]*\"answer\"[^{}]*\}", output, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    # Fallback: everything is the answer
    return {"answer": output.strip()}


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive a Teams Outgoing Webhook message."""
    body = request.get_data()
    auth = request.headers.get("Authorization", "")

    if not verify_teams_hmac(body, auth):
        return jsonify({"type": "message", "text": "❌ Unauthorized"}), 401

    data   = request.get_json(force=True, silent=True) or {}
    text   = data.get("text", "").strip()
    sender = (data.get("from") or {}).get("name", "Team member")

    # Strip HTML tags Teams injects (e.g. <at>BotName</at>)
    text = re.sub(r"<[^>]+>", "", text).strip()

    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {sender}: {text[:120]}")

    if not text:
        return jsonify({
            "type": "message",
            "text": "👋 Hi! Ask me anything about the sprint — tickets, status, quality, what the team is working on.",
        })

    # Respond immediately (Teams times out in 5s) and process async
    first_name = sender.split(",")[-1].strip().split()[0] if sender else "there"
    threading.Thread(
        target=run_claude_task,
        args=(text, sender),
        daemon=True,
    ).start()

    return jsonify({
        "type": "message",
        "text": f"⏳ On it, {first_name}! Give me a moment...",
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "bot": "PIF PM Assistant",
        "incoming_webhook": bool(INCOMING_WEBHOOK_URL),
        "hmac_enabled": bool(WEBHOOK_SECRET),
    })


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print()
    print("╔══════════════════════════════════════════════╗")
    print("║      PIF PM Assistant — Teams Bot            ║")
    print("╠══════════════════════════════════════════════╣")
    print(f"║  Webhook endpoint:  http://0.0.0.0:{PORT}/webhook  ║")
    print(f"║  Health check:      http://0.0.0.0:{PORT}/health   ║")
    print("║  Press Ctrl+C to stop                        ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    if not INCOMING_WEBHOOK_URL:
        print("⚠️  TEAMS_INCOMING_WEBHOOK_URL not set — responses printed to terminal only")
        print("   Set it in config.sh and re-run.\n")
    if not WEBHOOK_SECRET:
        print("⚠️  TEAMS_WEBHOOK_SECRET not set — HMAC verification disabled (dev mode)")
        print("   Set it in config.sh after creating the Outgoing Webhook.\n")

    print("Waiting for messages from Teams...\n")

    try:
        app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("\n\n👋 PIF Bot stopped.")


if __name__ == "__main__":
    # Resolve claude binary
    import shutil
    resolved = shutil.which("claude")
    if resolved:
        os.environ["CLAUDE_BIN"] = resolved
    CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
    main()
