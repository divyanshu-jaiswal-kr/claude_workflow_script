#!/bin/bash
# setup_launchd.sh
# Installs a macOS LaunchAgent that runs the PIF weekly update every Friday at 18:00.
# LaunchAgent is the recommended macOS approach — more reliable than cron,
# runs as the current user, and persists across reboots without any manual intervention.
#
# Usage:
#   ./setup_launchd.sh           # install (or reinstall) the LaunchAgent
#   ./setup_launchd.sh --unload  # stop and remove the LaunchAgent

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SCRIPT="$SCRIPT_DIR/run_weekly_update.sh"
LOG_DIR="$SCRIPT_DIR/logs"
LABEL="com.pif.weekly-confluence-update"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"

if [[ ! -x "$RUN_SCRIPT" ]]; then
  chmod +x "$RUN_SCRIPT"
fi

mkdir -p "$LOG_DIR"

# ── Unload / remove ───────────────────────────────────────────────────────────
if [[ "${1:-}" == "--unload" ]]; then
  if launchctl list | grep -q "$LABEL"; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    echo "LaunchAgent unloaded."
  fi
  if [[ -f "$PLIST_PATH" ]]; then
    rm "$PLIST_PATH"
    echo "Plist removed: $PLIST_PATH"
  else
    echo "No plist found at $PLIST_PATH — nothing to remove."
  fi
  exit 0
fi

# ── Write the plist ───────────────────────────────────────────────────────────
cat > "$PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <!-- Unique label for this job -->
    <key>Label</key>
    <string>${LABEL}</string>

    <!-- Script to run -->
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${RUN_SCRIPT}</string>
    </array>

    <!-- Every Friday at 18:00 (Weekday: 5 = Friday in launchd) -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>5</integer>
        <key>Hour</key>
        <integer>18</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <!-- Environment: give launchd the same PATH and HOME the user has -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>${HOME}</string>
        <key>USER</key>
        <string>$(whoami)</string>
        <key>PATH</key>
        <string>${HOME}/.local/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    </dict>

    <!-- Capture any output that escapes before run_weekly_update.sh sets up logging -->
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/launchd_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/launchd_stderr.log</string>

    <!-- Do NOT run at load time — only on schedule -->
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLIST

echo "Plist written: $PLIST_PATH"

# ── Unload old instance if running, then load ─────────────────────────────────
if launchctl list 2>/dev/null | grep -q "$LABEL"; then
  echo "Reloading existing LaunchAgent..."
  launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

launchctl load "$PLIST_PATH"
echo ""
echo "✅ LaunchAgent installed successfully."
echo "   Schedule: every Friday at 18:00"
echo "   Script:   $RUN_SCRIPT"
echo "   Logs:     $LOG_DIR/"
echo ""
echo "To verify it's loaded:  launchctl list | grep $LABEL"
echo "To run it right now:    launchctl start $LABEL"
echo "To remove it:           ./setup_launchd.sh --unload"
