#!/bin/bash
# run_weekly_update.sh
# Runs the PIF weekly Confluence update via Claude Code (non-interactive mode).
# Claude uses MCP tools directly for all Jira and Confluence API operations.
# Python scripts in scripts/ are available for local file processing only.
#
# Usage:
#   ./run_weekly_update.sh                                    # normal automated run (uses today's date + active sprint)
#   ./run_weekly_update.sh --dry-run                          # print the resolved prompt, do not execute
#   ./run_weekly_update.sh --week-end YYYY-MM-DD              # use a custom end date (week start computed from it)
#   ./run_weekly_update.sh --sprint "DCP 2026Q2.2"            # override sprint name (bypasses openSprints() JQL)
#   ./run_weekly_update.sh --week-end 2026-06-22 --sprint "DCP 2026Q2.2"   # both overrides together

set -euo pipefail

# ── Ensure claude is findable regardless of how this script is invoked ────────
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:$PATH"
export HOME="${HOME:-/Users/$(whoami)}"
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

# ── Parse optional flags ──────────────────────────────────────────────────────
CUSTOM_WEEK_END=""
SPRINT_OVERRIDE=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)    DRY_RUN=true; shift ;;
    --week-end)   CUSTOM_WEEK_END="$2"; shift 2 ;;
    --sprint)     SPRINT_OVERRIDE="$2"; shift 2 ;;
    *)            shift ;;
  esac
done
# ─────────────────────────────────────────────────────────────────────────────

# ── Compute week date range ───────────────────────────────────────────────────
# macOS date: %u = 1 (Mon) … 7 (Sun)
if [[ -n "$CUSTOM_WEEK_END" ]]; then
  WEEK_END="$CUSTOM_WEEK_END"
  # Compute the Monday of the week containing WEEK_END
  DOW=$(date -j -f "%Y-%m-%d" "$WEEK_END" +%u)
  DAYS_SINCE_MON=$(( DOW - 1 ))
  if [[ $DAYS_SINCE_MON -eq 0 ]]; then
    # WEEK_END is Monday — use the previous Monday as week start (full 7-day window)
    WEEK_START=$(date -j -v -7d -f "%Y-%m-%d" "$WEEK_END" +%Y-%m-%d)
  else
    WEEK_START=$(date -j -v -${DAYS_SINCE_MON}d -f "%Y-%m-%d" "$WEEK_END" +%Y-%m-%d)
  fi
else
  DOW=$(date +%u)
  DAYS_SINCE_MON=$(( DOW - 1 ))
  WEEK_START=$(date -v -${DAYS_SINCE_MON}d +%Y-%m-%d)
  WEEK_END=$(date +%Y-%m-%d)
fi
# ─────────────────────────────────────────────────────────────────────────────

# ── Substitute placeholders into the prompt ───────────────────────────────────
RESOLVED_PROMPT=$(sed \
  -e "s/WEEK_START_PLACEHOLDER/$WEEK_START/g" \
  -e "s/WEEK_END_PLACEHOLDER/$WEEK_END/g" \
  -e "s|SPRINT_OVERRIDE_PLACEHOLDER|$SPRINT_OVERRIDE|g" \
  "$PROMPT_FILE")
# ─────────────────────────────────────────────────────────────────────────────

if [[ "$DRY_RUN" == true ]]; then
  {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY RUN — workflow not executed"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Week start: $WEEK_START"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Week end:   $WEEK_END"
    [[ -n "$SPRINT_OVERRIDE" ]] && echo "[$(date '+%Y-%m-%d %H:%M:%S')] Sprint override: $SPRINT_OVERRIDE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Prompt file: $PROMPT_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Log file:    $LOG_FILE"
    echo ""
    echo "=== Resolved prompt ==="
    echo "$RESOLVED_PROMPT"
  } | tee -a "$LOG_FILE"
  exit 0
fi

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

log "Starting PIF weekly Confluence update (automated)"
log "Week: $WEEK_START → $WEEK_END"
[[ -n "$SPRINT_OVERRIDE" ]] && log "Sprint override: $SPRINT_OVERRIDE"
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
