#!/bin/bash
# setup_cron.sh
# Installs a weekly cron job to run the PIF Confluence update every Friday at 6:00 PM.
#
# Usage:
#   ./setup_cron.sh           # install the cron job
#   ./setup_cron.sh --remove  # remove the cron job

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SCRIPT="$SCRIPT_DIR/run_weekly_update.sh"
CRON_COMMENT="# PIF Weekly Confluence Update"
# Every Friday at 6:00 PM local time
CRON_SCHEDULE="0 18 * * 5"
# run_weekly_update.sh exports its own PATH and does its own timestamped logging in logs/
CRON_JOB="$CRON_SCHEDULE $RUN_SCRIPT >> /dev/null 2>&1"

if [[ ! -x "$RUN_SCRIPT" ]]; then
  echo "Making $RUN_SCRIPT executable..."
  chmod +x "$RUN_SCRIPT"
fi

if [[ "${1:-}" == "--remove" ]]; then
  echo "Removing PIF weekly update cron job..."
  # Remove lines containing the comment marker and the job line
  crontab -l 2>/dev/null \
    | grep -v "$CRON_COMMENT" \
    | grep -v "run_weekly_update.sh" \
    | crontab -
  echo "Cron job removed."
  exit 0
fi

# Check if already installed
if crontab -l 2>/dev/null | grep -q "run_weekly_update.sh"; then
  echo "Cron job already exists. Current entry:"
  crontab -l | grep "run_weekly_update.sh"
  echo ""
  echo "To update it, run: ./setup_cron.sh --remove && ./setup_cron.sh"
  exit 0
fi

echo "Installing cron job: $CRON_SCHEDULE (every Friday at 6:00 PM)"
echo "Script: $RUN_SCRIPT"
echo ""

# Append to existing crontab
(crontab -l 2>/dev/null; echo ""; echo "$CRON_COMMENT"; echo "$CRON_JOB") | crontab -

echo "Cron job installed successfully."
echo ""
echo "To verify: crontab -l"
echo "To remove:  ./setup_cron.sh --remove"
echo "To test now: $RUN_SCRIPT"
