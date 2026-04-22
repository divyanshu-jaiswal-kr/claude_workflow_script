#!/usr/bin/env bash
# run_command.sh — PIF PM Command Center
#
# Usage:
#   ./run_command.sh                           # read command page, run checked items
#   ./run_command.sh --command sprint_summary  # run one specific command
#   ./run_command.sh --command board_report
#   ./run_command.sh --command ticket_quality
#   ./run_command.sh --command fix_tickets
#   ./run_command.sh --command fix_descriptions
#   ./run_command.sh --command browse_folder
#   ./run_command.sh --command weekly_progress
#   ./run_command.sh --setup                   # one-time: create command center page
#   ./run_command.sh --dry-run                 # print what would run, no execution
#   ./run_command.sh --teams                   # start Teams bot (runs until Ctrl+C)

set -euo pipefail
IFS=$'\n\t'

# ── Ensure claude and python3 are findable ────────────────────────────────────
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:$PATH"
export HOME="${HOME:-/Users/$(whoami)}"
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load config and export everything so Python scripts can read it
source "$SCRIPT_DIR/config.sh"
export COMMAND_PAGE_ID COMMAND_PAGE_PARENT_ID WEEKLY_PAGE_ID CLOUD_ID
export PROJECT SPACE SPACE_ID EPIC_KEYS
export AC_FIELD SPRINT_FIELD STORY_POINTS_FIELD EPIC_LINK_FIELD BOARD_ID
export TEAMS_INCOMING_WEBHOOK_URL TEAMS_WEBHOOK_SECRET TEAMS_BOT_PORT
export CLAUDE_BIN

# Binary checks
CLAUDE_BIN="$(command -v claude 2>/dev/null || true)"
if [[ -z "$CLAUDE_BIN" || ! -x "$CLAUDE_BIN" ]]; then
  echo "ERROR: 'claude' binary not found in PATH." >&2
  exit 1
fi

if ! command -v python3 &>/dev/null; then
  echo "ERROR: 'python3' not found in PATH." >&2
  exit 1
fi

# Setup dirs
mkdir -p "$SCRIPT_DIR/logs" "$SCRIPT_DIR/output" "$SCRIPT_DIR/state"

# ── Date helpers ──────────────────────────────────────────────────────────────
DOW=$(date +%u)
DAYS_SINCE_MON=$(( DOW - 1 ))
WEEK_START=$(date -v -${DAYS_SINCE_MON}d +%Y-%m-%d)
WEEK_END=$(date +%Y-%m-%d)
TODAY="$WEEK_END"
# ─────────────────────────────────────────────────────────────────────────────

LOG_FILE="$SCRIPT_DIR/logs/command_$(date +%Y-%m-%d_%H-%M-%S).log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

# Render a prompt file with config substitutions → returns temp file path
render_prompt() {
  local src="$1"
  local tmp
  tmp="$(mktemp /tmp/pif_prompt.XXXXXX)"
  sed \
    -e "s|WEEK_START_PLACEHOLDER|$WEEK_START|g" \
    -e "s|WEEK_END_PLACEHOLDER|$WEEK_END|g" \
    -e "s|TODAY_PLACEHOLDER|$TODAY|g" \
    -e "s|COMMAND_PAGE_ID_PLACEHOLDER|$COMMAND_PAGE_ID|g" \
    -e "s|COMMAND_PAGE_PARENT_ID_PLACEHOLDER|$COMMAND_PAGE_PARENT_ID|g" \
    -e "s|WEEKLY_PAGE_ID_PLACEHOLDER|$WEEKLY_PAGE_ID|g" \
    -e "s|CLOUD_ID_PLACEHOLDER|$CLOUD_ID|g" \
    -e "s|PROJECT_PLACEHOLDER|$PROJECT|g" \
    -e "s|SPACE_PLACEHOLDER|$SPACE|g" \
    -e "s|SPACE_ID_PLACEHOLDER|$SPACE_ID|g" \
    -e "s|EPIC_KEYS_PLACEHOLDER|$EPIC_KEYS|g" \
    -e "s|AC_FIELD_PLACEHOLDER|$AC_FIELD|g" \
    -e "s|BOARD_ID_PLACEHOLDER|$BOARD_ID|g" \
    "$src" > "$tmp"
  echo "$tmp"
}

# Run a rendered prompt via Claude with pseudo-tty
run_prompt() {
  local prompt_file="$1"
  local _exit_file _wrapper
  _exit_file="$(mktemp /tmp/pif_exit.XXXXXX)"
  _wrapper="$(mktemp /tmp/pif_wrapper.XXXXXX)"

  cat > "$_wrapper" << WEOF
#!/bin/bash
"$CLAUDE_BIN" --dangerously-skip-permissions -p "\$(cat '$prompt_file')"
printf '%s' \$? > '$_exit_file'
WEOF
  chmod +x "$_wrapper"

  set +e
  script -q /dev/null "$_wrapper" 2>&1 | tee -a "$LOG_FILE"
  local exit_code
  exit_code=$(cat "$_exit_file" 2>/dev/null || echo "1")
  rm -f "$_exit_file" "$_wrapper"
  set -e
  return "$exit_code"
}

# Run a Python script, logging output
run_python() {
  local script="$1"
  shift
  log "  python3 $script $*"
  set +e
  python3 "$SCRIPT_DIR/scripts/$script" "$@" 2>&1 | tee -a "$LOG_FILE"
  local exit_code="${PIPESTATUS[0]}"
  set -e
  if [[ "$exit_code" -ne 0 ]]; then
    log "ERROR: python3 $script exited with code $exit_code"
    return "$exit_code"
  fi
}

# ── Execute a named command ───────────────────────────────────────────────────
execute_command() {
  local CMD="$1"

  case "$CMD" in

    sprint_summary)
      # Fully scripted — zero Claude tokens
      log "→ Fetching sprint data..."
      run_python fetch_sprint.py || return 1
      log "→ Posting sprint summary to Confluence..."
      run_python sprint_summary_post.py || return 1
      ;;

    board_report)
      log "→ Fetching board data (sprint tickets + comments)..."
      run_python fetch_board.py || return 1
      log "→ Generating member summaries (Claude)..."
      local TMP_PROMPT
      TMP_PROMPT="$(render_prompt "$SCRIPT_DIR/prompts/board_report.md")"
      run_prompt "$TMP_PROMPT" || { rm -f "$TMP_PROMPT"; return 1; }
      rm -f "$TMP_PROMPT"
      log "→ Posting board report to Confluence..."
      run_python board_report_post.py || return 1
      ;;

    ticket_quality)
      # Determine scope from execution plan
      SCOPE=$(python3 -c "
import json, sys
try:
    d = json.load(open('$SCRIPT_DIR/state/execution_plan.json'))
    print(d.get('config', {}).get('ticket_quality_scope', 'sprint'))
except: print('sprint')
" 2>/dev/null || echo "sprint")

      if [[ "$SCOPE" == "backlog" || "$SCOPE" == "all" ]]; then
        log "→ Fetching backlog data (scope=$SCOPE)..."
        run_python fetch_backlog.py || return 1
      else
        log "→ Fetching board data (scope=$SCOPE)..."
        run_python fetch_board.py || return 1
      fi

      log "→ Auditing ticket quality (Claude)..."
      local TMP_PROMPT
      TMP_PROMPT="$(render_prompt "$SCRIPT_DIR/prompts/ticket_quality.md")"
      run_prompt "$TMP_PROMPT" || { rm -f "$TMP_PROMPT"; return 1; }
      rm -f "$TMP_PROMPT"
      log "→ Posting ticket quality report to Confluence..."
      run_python ticket_quality_post.py || return 1
      ;;

    fix_tickets|fix_descriptions)
      log "→ Fetching board data for fix targets..."
      run_python fetch_board.py || return 1
      log "→ Drafting description + AC improvements (Claude)..."
      local TMP_PROMPT
      TMP_PROMPT="$(render_prompt "$SCRIPT_DIR/prompts/fix_tickets.md")"
      run_prompt "$TMP_PROMPT" || { rm -f "$TMP_PROMPT"; return 1; }
      rm -f "$TMP_PROMPT"
      # Note: apply_ticket_fixes.py patches Jira — user must confirm this is intended.
      # Uncomment the line below to auto-apply; by default just prints the plan.
      # run_python apply_ticket_fixes.py || return 1
      log "ℹ️  Fixes drafted in output/ticket_fixes.json. Review before applying."
      log "   To apply: python3 scripts/apply_ticket_fixes.py"
      ;;

    weekly_progress)
      log "Delegating to run_weekly_update.sh..."
      if [[ -x "$SCRIPT_DIR/run_weekly_update.sh" ]]; then
        "$SCRIPT_DIR/run_weekly_update.sh" 2>&1 | tee -a "$LOG_FILE"
      else
        log "ERROR: run_weekly_update.sh not found or not executable."
        return 1
      fi
      ;;

    browse_folder)
      local TMP_PROMPT
      TMP_PROMPT="$(render_prompt "$SCRIPT_DIR/prompts/browse_folder.md")"
      run_prompt "$TMP_PROMPT"
      rm -f "$TMP_PROMPT"
      ;;

    *)
      # Generic fallback: try prompts/<cmd>.md if it exists
      local PROMPT_SRC="$SCRIPT_DIR/prompts/${CMD}.md"
      if [[ -f "$PROMPT_SRC" ]]; then
        log "→ Running prompt for '$CMD'..."
        local TMP_PROMPT
        TMP_PROMPT="$(render_prompt "$PROMPT_SRC")"
        run_prompt "$TMP_PROMPT"
        rm -f "$TMP_PROMPT"
      else
        log "ERROR: Unknown command '$CMD' and no prompt file found at $PROMPT_SRC"
        return 1
      fi
      ;;
  esac
}

# ── Parse flags ───────────────────────────────────────────────────────────────
COMMAND=""
DO_SETUP=false
DRY_RUN=false
DO_TEAMS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --setup)   DO_SETUP=true; shift ;;
    --command) COMMAND="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --teams)   DO_TEAMS=true; shift ;;
    *) echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
done
# ─────────────────────────────────────────────────────────────────────────────

# ── Teams bot mode ────────────────────────────────────────────────────────────
if $DO_TEAMS; then
  echo "Starting PIF Teams bot on port ${TEAMS_BOT_PORT:-3978}..."
  if ! python3 -c "import flask" &>/dev/null; then
    echo "Installing Flask..."
    pip3 install flask --quiet
  fi
  export CLAUDE_BIN
  exec python3 "$SCRIPT_DIR/scripts/teams_bot.py"
fi
# ─────────────────────────────────────────────────────────────────────────────

# ── Dry-run mode ──────────────────────────────────────────────────────────────
if $DRY_RUN; then
  {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY RUN — workflow not executed"
    echo "  COMMAND_PAGE_ID:  ${COMMAND_PAGE_ID:-<not set>}"
    echo "  WEEK_START:       $WEEK_START"
    echo "  WEEK_END:         $WEEK_END"
    echo "  SPACE:            $SPACE"
    echo "  EPIC_KEYS:        $EPIC_KEYS"
    echo "  AC_FIELD:         $AC_FIELD"
    echo ""
    if $DO_SETUP; then
      echo "  Would run: prompts/setup_command_page.md (Claude)"
    elif [[ -n "$COMMAND" ]]; then
      echo "  Would run: command '$COMMAND'"
    else
      echo "  Would run: scripts/dispatcher.py → execution_plan.json → each checked command"
    fi
    echo "  Log: $LOG_FILE"
  } | tee -a "$LOG_FILE"
  exit 0
fi
# ─────────────────────────────────────────────────────────────────────────────

# ── Setup mode ────────────────────────────────────────────────────────────────
if $DO_SETUP; then
  log "Running setup: creating PIF command center page in Confluence"
  PROMPT_SRC="$SCRIPT_DIR/prompts/setup_command_page.md"
  [[ -f "$PROMPT_SRC" ]] || { echo "ERROR: Missing $PROMPT_SRC" >&2; exit 1; }
  TMP_PROMPT="$(render_prompt "$PROMPT_SRC")"
  if run_prompt "$TMP_PROMPT"; then
    log "Setup complete. Copy the page ID printed above into config.sh as COMMAND_PAGE_ID."
  else
    log "ERROR: Setup failed."
    rm -f "$TMP_PROMPT"
    exit 1
  fi
  rm -f "$TMP_PROMPT"
  exit 0
fi
# ─────────────────────────────────────────────────────────────────────────────

# ── Single command mode ───────────────────────────────────────────────────────
if [[ -n "$COMMAND" ]]; then
  log "Running command: $COMMAND"
  if execute_command "$COMMAND"; then
    log "✅ Command '$COMMAND' completed."
  else
    log "❌ Command '$COMMAND' failed."
    exit 1
  fi
  exit 0
fi
# ─────────────────────────────────────────────────────────────────────────────

# ── Default: dispatcher mode ──────────────────────────────────────────────────
if [[ -z "$COMMAND_PAGE_ID" ]]; then
  echo "ERROR: COMMAND_PAGE_ID is not set in config.sh." >&2
  echo "Run './run_command.sh --setup' first to create the command page, then set the ID." >&2
  exit 1
fi

log "Running dispatcher (Python, no Claude)..."
if ! run_python dispatcher.py; then
  log "ERROR: Dispatcher failed."
  exit 1
fi
log "Dispatcher completed."

# Read execution plan
PLAN_FILE="$SCRIPT_DIR/state/execution_plan.json"
if [[ ! -f "$PLAN_FILE" ]]; then
  log "No execution plan found at $PLAN_FILE. Nothing to run."
  exit 0
fi

# Extract commands list
COMMANDS=$(python3 -c "
import json, sys
try:
    d = json.load(open('$PLAN_FILE'))
    cmds = d.get('commands', [])
    print('\n'.join(cmds))
except Exception as e:
    sys.exit(0)
" 2>/dev/null || true)

# Extract custom tasks count
CUSTOM_TASK_COUNT=$(python3 -c "
import json
try:
    d = json.load(open('$PLAN_FILE'))
    print(len(d.get('custom_tasks', [])))
except: print(0)
" 2>/dev/null || echo "0")

if [[ -z "$COMMANDS" && "$CUSTOM_TASK_COUNT" -eq 0 ]]; then
  log "No commands in execution plan. Done."
  exit 0
fi

log "Commands to run: $(echo "$COMMANDS" | tr '\n' ' ' | sed 's/ $//')"

# ── Execute each command ──────────────────────────────────────────────────────
while IFS= read -r CMD; do
  [[ -z "$CMD" ]] && continue
  log "═══════════════════════════════════"
  log "▶ Running: $CMD"
  log "═══════════════════════════════════"
  if execute_command "$CMD"; then
    log "✅ $CMD completed."
  else
    log "❌ $CMD failed. Stopping."
    exit 1
  fi
done <<< "$COMMANDS"

# ── Execute custom tasks (each routed through Claude with MCP) ────────────────
if [[ "$CUSTOM_TASK_COUNT" -gt 0 ]]; then
  log "═══════════════════════════════════"
  log "▶ Running $CUSTOM_TASK_COUNT custom task(s) from Confluence comments"
  log "═══════════════════════════════════"

  python3 - <<PYEOF
import json, subprocess, tempfile, os
from pathlib import Path

plan = json.load(open('$PLAN_FILE'))
tasks = plan.get('custom_tasks', [])
template = open('$SCRIPT_DIR/prompts/custom_task.md').read()

# Build a bullet list of output files that exist right now
output_dir = Path('$SCRIPT_DIR/output')
DATA_FILES = {
    'sprint.json':   'Sprint ticket list (status, assignee, epic, story points)',
    'board.json':    'Sprint tickets with full description, AC, and all comments',
    'backlog.json':  'Backlog (To Do) tickets with description and AC',
}
available_lines = []
for fname, desc in DATA_FILES.items():
    fpath = output_dir / fname
    if fpath.exists():
        import datetime
        mtime = datetime.datetime.fromtimestamp(fpath.stat().st_mtime).strftime('%H:%M')
        available_lines.append(f'- `output/{fname}` — {desc} _(fetched {mtime})_')
if available_lines:
    available_data = '\n'.join(available_lines)
else:
    available_data = '_No output files fetched yet this session. Run a fetch script or use MCP tools._'

# Standard placeholder substitutions
substitutions = {
    'SPACE_ID_PLACEHOLDER':               '$SPACE_ID',
    'EPIC_KEYS_PLACEHOLDER':              '$EPIC_KEYS',
    'COMMAND_PAGE_ID_PLACEHOLDER':        '$COMMAND_PAGE_ID',
    'COMMAND_PAGE_PARENT_ID_PLACEHOLDER': '$COMMAND_PAGE_PARENT_ID',
    'AVAILABLE_DATA_PLACEHOLDER':         available_data,
}

for t in tasks:
    instruction = t.get('instruction', '').strip()
    if not instruction:
        continue
    task_id = t.get('id', '?')
    print(f"→ Custom task {task_id}: {instruction[:80]}...")

    body = template
    for placeholder, value in substitutions.items():
        body = body.replace(placeholder, value)
    body = body.replace('CUSTOM_INSTRUCTION_PLACEHOLDER', instruction)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(body)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ['$CLAUDE_BIN', '--dangerously-skip-permissions', '-p', open(tmp_path).read()],
            capture_output=False,
        )
        if result.returncode != 0:
            print(f"  ⚠  Custom task {task_id} exited with code {result.returncode}")
    finally:
        os.unlink(tmp_path)
PYEOF

fi

log "✅ All commands completed."
