#!/usr/bin/env bash
# run_command.sh — PIF PM Command Center
#
# Usage:
#   ./run_command.sh                           # read command page, run checked items
#   ./run_command.sh --command sprint_summary  # run one specific command
#   ./run_command.sh --command board_report
#   ./run_command.sh --command ticket_quality
#   ./run_command.sh --command fix_descriptions
#   ./run_command.sh --command browse_folder
#   ./run_command.sh --command weekly_progress
#   ./run_command.sh --setup                   # one-time: create command center page
#   ./run_command.sh --dry-run                 # print what would run, no execution

set -euo pipefail
IFS=$'\n\t'

# ── Ensure claude is findable regardless of how this script is invoked ────────
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:$PATH"
export HOME="${HOME:-/Users/$(whoami)}"
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load config
source "$SCRIPT_DIR/config.sh"

# Binary check
CLAUDE_BIN="$(command -v claude 2>/dev/null || true)"
if [[ -z "$CLAUDE_BIN" || ! -x "$CLAUDE_BIN" ]]; then
  echo "ERROR: 'claude' binary not found in PATH. Install Claude Code or set PATH correctly." >&2
  exit 1
fi

# Setup dirs
mkdir -p "$SCRIPT_DIR/logs" "$SCRIPT_DIR/output" "$SCRIPT_DIR/state"

# ── Compute date range (last Monday → today) ─────────────────────────────────
DOW=$(date +%u)
DAYS_SINCE_MON=$(( DOW - 1 ))
WEEK_START=$(date -v -${DAYS_SINCE_MON}d +%Y-%m-%d)
WEEK_END=$(date +%Y-%m-%d)
TODAY="$WEEK_END"
# ─────────────────────────────────────────────────────────────────────────────

LOG_FILE="$SCRIPT_DIR/logs/command_$(date +%Y-%m-%d_%H-%M-%S).log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

# Render a prompt file with all config substitutions → returns temp file path
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

# Run a rendered prompt via Claude with pseudo-tty → returns exit code
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

# ── Parse flags ───────────────────────────────────────────────────────────────
COMMAND=""
DO_SETUP=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --setup)   DO_SETUP=true; shift ;;
    --command) COMMAND="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    *) echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
done
# ─────────────────────────────────────────────────────────────────────────────

# ── Dry-run mode ──────────────────────────────────────────────────────────────
if $DRY_RUN; then
  {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY RUN — workflow not executed"
    echo "  COMMAND_PAGE_ID:  ${COMMAND_PAGE_ID:-<not set>}"
    echo "  WEEK_START:       $WEEK_START"
    echo "  WEEK_END:         $WEEK_END"
    echo "  TODAY:            $TODAY"
    echo "  SPACE_ID:         $SPACE_ID"
    echo "  AC_FIELD:         $AC_FIELD"
    echo "  EPIC_KEYS:        $EPIC_KEYS"
    echo ""
    if $DO_SETUP; then
      echo "  Would run: prompts/setup_command_page.md"
    elif [[ -n "$COMMAND" ]]; then
      echo "  Would run: prompts/${COMMAND}.md"
    else
      echo "  Would run: dispatcher → state/execution_plan.json → each checked command"
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
  PROMPT_SRC="$SCRIPT_DIR/prompts/${COMMAND}.md"
  [[ -f "$PROMPT_SRC" ]] || { echo "ERROR: No prompt for command '$COMMAND' at $PROMPT_SRC" >&2; exit 1; }
  log "Running command: $COMMAND"
  TMP_PROMPT="$(render_prompt "$PROMPT_SRC")"
  if run_prompt "$TMP_PROMPT"; then
    log "✅ Command '$COMMAND' completed."
  else
    log "❌ Command '$COMMAND' failed."
    rm -f "$TMP_PROMPT"
    exit 1
  fi
  rm -f "$TMP_PROMPT"
  exit 0
fi
# ─────────────────────────────────────────────────────────────────────────────

# ── Default: dispatcher mode ──────────────────────────────────────────────────
if [[ -z "$COMMAND_PAGE_ID" ]]; then
  echo "ERROR: COMMAND_PAGE_ID is not set in config.sh." >&2
  echo "Run './run_command.sh --setup' first to create the command page, then set the ID." >&2
  exit 1
fi

log "Running dispatcher (command page: $COMMAND_PAGE_ID)"
TMP_PROMPT="$(render_prompt "$SCRIPT_DIR/prompts/dispatcher.md")"
if run_prompt "$TMP_PROMPT"; then
  log "Dispatcher completed."
else
  log "ERROR: Dispatcher failed."
  rm -f "$TMP_PROMPT"
  exit 1
fi
rm -f "$TMP_PROMPT"

# Read execution plan written by dispatcher
PLAN_FILE="$SCRIPT_DIR/state/execution_plan.json"
if [[ ! -f "$PLAN_FILE" ]]; then
  log "No execution plan found at $PLAN_FILE. Nothing to run."
  exit 0
fi

COMMANDS=$(python3 -c "
import json, sys
try:
    d = json.load(open('$PLAN_FILE'))
    cmds = d.get('commands', [])
    print('\n'.join(cmds))
except Exception as e:
    sys.exit(0)
" 2>/dev/null || true)

if [[ -z "$COMMANDS" ]]; then
  log "No commands in execution plan. Done."
  exit 0
fi

log "Commands to run: $(echo "$COMMANDS" | tr '\n' ' ')"

FAILED_CMDS=""
while IFS= read -r CMD; do
  [[ -z "$CMD" ]] && continue
  PROMPT_SRC="$SCRIPT_DIR/prompts/${CMD}.md"
  if [[ ! -f "$PROMPT_SRC" ]]; then
    log "WARNING: No prompt file for command '$CMD'. Skipping."
    continue
  fi
  log "═══════════════════════════════════"
  log "▶ Running: $CMD"
  log "═══════════════════════════════════"
  TMP_PROMPT="$(render_prompt "$PROMPT_SRC")"
  if run_prompt "$TMP_PROMPT"; then
    log "✅ $CMD completed."
  else
    log "❌ $CMD failed."
    FAILED_CMDS="$FAILED_CMDS $CMD"
    rm -f "$TMP_PROMPT"
    log "Stopping on failure. Fix '$CMD' and re-run."
    exit 1
  fi
  rm -f "$TMP_PROMPT"
done <<< "$COMMANDS"

if [[ -n "$FAILED_CMDS" ]]; then
  log "Commands failed:$FAILED_CMDS"
  exit 1
else
  log "✅ All commands completed."
fi
