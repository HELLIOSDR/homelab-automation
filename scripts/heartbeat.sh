#!/bin/bash
# heartbeat.sh — wysyła ping do homelab co 5 min
# Instalacja: crontab -e → */5 * * * * bash ~/homelab-automation/scripts/heartbeat.sh

HEARTBEAT_URL="${HOMELAB_WEBHOOK_URL:-}"
AGENT_NAME="${AGENT_NAME:-Helios}"
LOG="$HOME/.claude/heartbeat.log"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

mkdir -p "$(dirname "$LOG")"

# Sprawdź czy Claude Code żyje (czy jest aktywna sesja)
CLAUDE_ALIVE=false
if pgrep -f "claude" > /dev/null 2>&1; then
  CLAUDE_ALIVE=true
fi

# Log lokalny
echo "$TIMESTAMP alive=true claude=$CLAUDE_ALIVE" >> "$LOG"

# Wyślij do homelab jeśli URL ustawiony
if [ -n "$HEARTBEAT_URL" ]; then
  curl -s -X POST "$HEARTBEAT_URL/heartbeat" \
    -H "Content-Type: application/json" \
    -d "{\"agent\":\"$AGENT_NAME\",\"timestamp\":\"$TIMESTAMP\",\"claude_alive\":$CLAUDE_ALIVE}" \
    --max-time 5 > /dev/null 2>&1 || true
fi

# Rotuj log jeśli > 1MB
if [ -f "$LOG" ] && [ $(wc -c < "$LOG") -gt 1048576 ]; then
  tail -500 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi
