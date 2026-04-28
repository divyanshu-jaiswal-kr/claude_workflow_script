#!/bin/bash
# run_next_steps_update.sh
# Every Tuesday: fetches next sprint "Open" tickets for the PIF team and updates
# the Next Steps column in the latest Confluence table automatically.
#
# Usage:
#   ./run_next_steps_update.sh              # run only if today is Tuesday
#   ./run_next_steps_update.sh --force      # run regardless of day
#   ./run_next_steps_update.sh --dry-run    # print resolved prompt, do not execute
#   ./run_next_steps_update.sh --install    # install macOS launchd agent (Tue 09:00)
#   ./run_next_steps_update.sh --uninstall  # remove launchd agent

set -euo pipefail

export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:$PATH"
export HOME="${HOME:-/Users/$(whoami)}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPT_FILE="$SCRIPT_DIR/next_steps_prompt.md"
LOG_DIR="$SCRIPT_DIR/logs"
PLIST_LABEL="com.pif.next-steps-update"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

mkdir -p "$LOG_DIR" "$SCRIPT_DIR/output"

# ── Install launchd agent (runs every Tuesday at 09:00) ─────────────────────
if [[ "${1:-}" == "--install" ]]; then
  cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>             <string>${PLIST_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${SCRIPT_DIR}/run_next_steps_update.sh</string>
    <string>--force</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key> <integer>2</integer>
    <key>Hour</key>    <integer>9</integer>
    <key>Minute</key>  <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>  <string>${LOG_DIR}/next_steps_launchd.log</string>
  <key>StandardErrorPath</key> <string>${LOG_DIR}/next_steps_launchd.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key> <string>${HOME}</string>
    <key>PATH</key> <string>${HOME}/.local/bin:/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
EOF
  launchctl load "$PLIST_PATH"
  echo "✅ Installed: ${PLIST_LABEL} — runs every Tuesday at 09:00"
  echo "   Plist: $PLIST_PATH"
  echo "   Log:   ${LOG_DIR}/next_steps_launchd.log"
  echo ""
  echo "   To run immediately:  launchctl start ${PLIST_LABEL}"
  echo "   To remove:          ./run_next_steps_update.sh --uninstall"
  exit 0
fi

# ── Remove launchd agent ──────────────────────────────────────────────────────
if [[ "${1:-}" == "--uninstall" ]]; then
  if [[ -f "$PLIST_PATH" ]]; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
    echo "✅ Uninstalled: ${PLIST_LABEL}"
  else
    echo "Not installed (plist not found at $PLIST_PATH)"
  fi
  exit 0
fi

# ── Tuesday guard (skip unless --force or --dry-run) ─────────────────────────
ARG="${1:-}"
if [[ "$ARG" != "--force" && "$ARG" != "--dry-run" ]]; then
  DOW=$(date +%u)   # 1=Mon … 7=Sun; Tuesday = 2
  if [[ "$DOW" -ne 2 ]]; then
    echo "Skipping: today is not Tuesday (weekday $DOW). Use --force to override."
    exit 0
  fi
fi

# ── Preflight checks ─────────────────────────────────────────────────────────
CLAUDE_BIN="$(command -v claude 2>/dev/null || true)"
if [[ -z "$CLAUDE_BIN" || ! -x "$CLAUDE_BIN" ]]; then
  echo "ERROR: 'claude' binary not found in PATH. Install Claude Code or set PATH correctly." >&2
  exit 1
fi

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "ERROR: Prompt file not found at $PROMPT_FILE" >&2
  exit 1
fi

# ── Resolve prompt — substitute today's date ──────────────────────────────────
TODAY=$(date +%Y-%m-%d)
RESOLVED_PROMPT=$(sed "s/TODAY_PLACEHOLDER/$TODAY/g" "$PROMPT_FILE")

# ── Dry run ──────────────────────────────────────────────────────────────────
LOG_FILE="$LOG_DIR/next_steps_$(date +%Y-%m-%d_%H-%M-%S).log"

if [[ "$ARG" == "--dry-run" ]]; then
  {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY RUN — not executed"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Today: $TODAY"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Prompt file: $PROMPT_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Log file: $LOG_FILE"
    echo ""
    echo "=== Resolved prompt ==="
    echo "$RESOLVED_PROMPT"
  } | tee -a "$LOG_FILE"
  exit 0
fi

# ── Full run ──────────────────────────────────────────────────────────────────
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

log "Starting PIF next sprint Next Steps update"
log "Today: $TODAY | Log: $LOG_FILE"

_PROMPT_FILE=$(mktemp /tmp/pif_next_steps_prompt.XXXXXX.md)
_EXIT_FILE=$(mktemp /tmp/pif_next_steps_exit.XXXXXX)
_WRAPPER=$(mktemp /tmp/pif_next_steps_wrapper.XXXXXX.sh)
printf '%s' "$RESOLVED_PROMPT" > "$_PROMPT_FILE"

cat > "$_WRAPPER" << WRAPPER_EOF
#!/bin/bash
"$CLAUDE_BIN" --dangerously-skip-permissions -p "\$(cat '$_PROMPT_FILE')"
printf '%s' \$? > '$_EXIT_FILE'
WRAPPER_EOF
chmod +x "$_WRAPPER"

set +e
script -q /dev/null "$_WRAPPER" 2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=$(cat "$_EXIT_FILE" 2>/dev/null || echo "1")
rm -f "$_PROMPT_FILE" "$_EXIT_FILE" "$_WRAPPER"
set -e

if [[ $EXIT_CODE -eq 0 ]]; then
  log "Completed successfully."
else
  log "ERROR: Workflow exited with code $EXIT_CODE."
fi

exit $EXIT_CODE
