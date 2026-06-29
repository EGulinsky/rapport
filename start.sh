#!/usr/bin/env bash
# start.sh — startet alle lokalen Bridges und dann die Docker-Container
set -euo pipefail

BRIDGES=(
  "com.jobtracker.files-bridge:9998"
  "com.jobtracker.calls-bridge:9997"
  "com.jobtracker.notesbridge:9999"
)

_bridge_running() {
  local port=$1
  lsof -i ":$port" -sTCP:LISTEN -t &>/dev/null
}

echo "==> Bridges prüfen und starten…"
for entry in "${BRIDGES[@]}"; do
  label="${entry%%:*}"
  port="${entry##*:}"
  if _bridge_running "$port"; then
    echo "    ✓ $label (Port $port läuft bereits)"
  else
    echo "    ↑ $label starten…"
    launchctl kickstart -k "gui/$(id -u)/$label" 2>/dev/null \
      || launchctl start "$label" 2>/dev/null \
      || true
    # kurz warten
    for i in $(seq 1 10); do
      sleep 0.5
      if _bridge_running "$port"; then
        echo "    ✓ $label gestartet (Port $port)"
        break
      fi
    done
    if ! _bridge_running "$port"; then
      echo "    ✗ $label konnte nicht gestartet werden — weiter trotzdem"
    fi
  fi
done

echo ""
echo "==> Docker Container starten…"
docker compose up -d

echo ""
echo "==> Fertig."
echo "    Backend:  http://localhost:8000"
echo "    Frontend: http://localhost:3000"
