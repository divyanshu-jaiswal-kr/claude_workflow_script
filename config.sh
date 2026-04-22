#!/usr/bin/env bash
# config.sh — PIF workflow configuration
# Sourced by run_command.sh. Edit values here; do not edit run_command.sh directly.

# ── Fill this in after running ./run_command.sh --setup ──────────────────────
COMMAND_PAGE_ID="1112081347"
# ─────────────────────────────────────────────────────────────────────────────

COMMAND_PAGE_PARENT_ID="1112015485"
WEEKLY_PAGE_ID="514261050"
CLOUD_ID="kroger.atlassian.net"
PROJECT="DCPFS"
SPACE="apiprogram"
SPACE_ID="112984070"
EPIC_KEYS="DCPFS-27809,DCPFS-27807,DCPFS-27772,DCPFS-27778"

# Jira custom field IDs (verified against DCPFS project)
AC_FIELD="customfield_10147"       # Acceptance Criteria
SPRINT_FIELD="customfield_10020"   # Sprint
STORY_POINTS_FIELD="customfield_10032"
EPIC_LINK_FIELD="customfield_10014"  # Epic Link (use "Epic Link" in JQL)

BOARD_ID="4896"

# ── Teams Bot ─────────────────────────────────────────────────────────────────
# 1. Teams channel → ··· → Connectors → Incoming Webhook → create → copy URL below
TEAMS_INCOMING_WEBHOOK_URL=""
# 2. Teams → Apps → Outgoing Webhooks → create → copy HMAC secret below
TEAMS_WEBHOOK_SECRET=""
# 3. Port the bot listens on (default 3978)
TEAMS_BOT_PORT="3978"
# ─────────────────────────────────────────────────────────────────────────────
