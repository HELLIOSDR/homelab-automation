#!/bin/bash
# setup-cron.sh — instaluje heartbeat jako cron job
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HEARTBEAT="$SCRIPT_DIR/heartbeat.sh"

(crontab -l 2>/dev/null | grep -v heartbeat; echo "*/5 * * * * bash $HEARTBEAT") | crontab -
echo "Heartbeat zainstalowany (co 5 min)"
echo "Log: ~/.claude/heartbeat.log"
crontab -l | grep heartbeat
