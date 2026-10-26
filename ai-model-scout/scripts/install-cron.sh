#!/usr/bin/env bash
# Adds a weekly cron entry (Sundays 07:00) for AI Model Scout on Linux/macOS.
# Usage: scripts/install-cron.sh ["MIN HOUR * * DOW"]
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCHEDULE="${1:-0 7 * * 0}"
PY="$APP_DIR/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
LINE="$SCHEDULE cd \"$APP_DIR\" && \"$PY\" -m scout >> \"$APP_DIR/reports/scout.log\" 2>&1"
mkdir -p "$APP_DIR/reports"
( crontab -l 2>/dev/null | grep -v "ai-model-scout\|-m scout" ; echo "$LINE # ai-model-scout" ) | crontab -
echo "Installed: $LINE"
