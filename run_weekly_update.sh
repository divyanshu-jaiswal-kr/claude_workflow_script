#!/bin/bash
# run_weekly_update.sh
# Runs the PIF weekly Confluence update via Claude Code (non-interactive mode).
# Claude uses MCP tools directly for all Jira and Confluence API operations.
# Python scripts in scripts/ are available for local file processing only.
#
# Usage:
#   ./run_weekly_update.sh              # normal automated run
#   ./run_weekly_update.sh --dry-run    # print the resolved prompt, do not execute

set -euo pipefail

# ── Ensure claude is findable regardless of how this script is invoked ────────
# cron and launchd start with a minimal PATH; add all common install locations.
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:$PATH"
export HOME="${HOME:-/Users/$(whoami)}"   # launchd may not set HOME
# ─────────────────────────────────────────────────────────────────────────────

CLAUDE_BIN="$(command -v claude 2>/dev/null || true)"
if [[ -z "$CLAUDE_BIN" || ! -x "$CLAUDE_BIN" ]]; then
  echo "ERROR: 'claude' binary not found in PATH. Install Claude Code or set PATH correctly." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPT_FILE="$SCRIPT_DIR/weekly_update_prompt.md"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/weekly_update_$(date +%Y-%m-%d_%H-%M-%S).log"

mkdir -p "$LOG_DIR" "$SCRIPT_DIR/output"

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "ERROR: Prompt file not found at $PROMPT_FILE" >&2
  exit 1
fi

# ── Compute week date range (last Monday → today) ────────────────────────────
# macOS date: %u = 1 (Mon) … 7 (Sun)
DOW=$(date +%u)
DAYS_SINCE_MON=$(( DOW - 1 ))
WEEK_START=$(date -v -${DAYS_SINCE_MON}d +%Y-%m-%d)
WEEK_END=$(date +%Y-%m-%d)
# ─────────────────────────────────────────────────────────────────────────────

# Substitute date placeholders into the prompt
RESOLVED_PROMPT=$(sed \
  -e "s/WEEK_START_PLACEHOLDER/$WEEK_START/g" \
  -e "s/WEEK_END_PLACEHOLDER/$WEEK_END/g" \
  "$PROMPT_FILE")

if [[ "${1:-}" == "--dry-run" ]]; then
  {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY RUN — workflow not executed"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Week start (last Monday): $WEEK_START"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Week end   (today):       $WEEK_END"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Prompt file: $PROMPT_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Log file:    $LOG_FILE"
    echo ""
    echo "=== Resolved prompt (with dates substituted) ==="
    echo "$RESOLVED_PROMPT"
  } | tee -a "$LOG_FILE"
  exit 0
fi

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

log "Starting PIF weekly Confluence update (automated)"
log "Week: $WEEK_START → $WEEK_END"
log "Log: $LOG_FILE"

# Write resolved prompt to a temp file — avoids quoting issues inside the wrapper script.
_PROMPT_FILE=$(mktemp /tmp/pif_prompt.XXXXXX.md)
_EXIT_FILE=$(mktemp /tmp/pif_exit.XXXXXX)
_WRAPPER=$(mktemp /tmp/pif_wrapper.XXXXXX.sh)
printf '%s' "$RESOLVED_PROMPT" > "$_PROMPT_FILE"

# Write a small wrapper that claude will run inside the pseudo-tty.
# Capturing the exit code separately because macOS `script` always exits 0.
cat > "$_WRAPPER" << WRAPPER_EOF
#!/bin/bash
"$CLAUDE_BIN" --dangerously-skip-permissions -p "\$(cat '$_PROMPT_FILE')"
printf '%s' \$? > '$_EXIT_FILE'
WRAPPER_EOF
chmod +x "$_WRAPPER"

# Run inside `script -q /dev/null` to give Claude a pseudo-tty.
# This forces line-buffered (real-time) output instead of block-buffered output through a pipe.
set +e
script -q /dev/null "$_WRAPPER" 2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=$(cat "$_EXIT_FILE" 2>/dev/null || echo "1")
rm -f "$_PROMPT_FILE" "$_EXIT_FILE" "$_WRAPPER"
set -e

if [[ $EXIT_CODE -eq 0 ]]; then
  log "Workflow completed successfully."
else
  log "ERROR: Workflow exited with code $EXIT_CODE."
fi

exit $EXIT_CODE
