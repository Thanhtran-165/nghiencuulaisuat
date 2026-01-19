#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

STATE_DIR="${STATE_DIR:-${HOME}/Library/Application Support/vn-bond-lab}"
mkdir -p "${STATE_DIR}/logs" "${STATE_DIR}/raw" "${STATE_DIR}/pids"

mkdir -p "${HOME}/Library/LaunchAgents"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8001}"
FRONTEND_PORT="${FRONTEND_PORT:-3002}"

PY_BIN="${PY_BIN:-}"
if [[ -z "${PY_BIN}" ]]; then
  if command -v python3.11 >/dev/null 2>&1; then
    PY_BIN="$(command -v python3.11)"
  else
    PY_BIN="$(command -v python3)"
  fi
fi

PLIST_SERVER_ID="com.vn-bond-lab.server"
PLIST_FRONTEND_ID="com.vn-bond-lab.frontend"

PLIST_SERVER_PATH="${HOME}/Library/LaunchAgents/${PLIST_SERVER_ID}.plist"
PLIST_FRONTEND_PATH="${HOME}/Library/LaunchAgents/${PLIST_FRONTEND_ID}.plist"

# IMPORTANT:
# - Avoid executing scripts inside iCloud Drive paths; some macOS setups block that for LaunchAgents.
# - Run python/node directly, and write DB/logs to STATE_DIR.
# - We also disable python bytecode writes to avoid __pycache__ under iCloud.

cat >"${PLIST_SERVER_PATH}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>${PLIST_SERVER_ID}</string>

    <key>ProgramArguments</key>
    <array>
      <string>/bin/zsh</string>
      <string>-lc</string>
      <string>cd "${STATE_DIR}" &amp;&amp; exec env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${ROOT_DIR}" DB_PATH="${STATE_DIR}/bonds.duckdb" RAW_DATA_PATH="${STATE_DIR}/raw" LOG_LEVEL=INFO "${PY_BIN}" -m uvicorn app.main:app --host "${HOST}" --port "${PORT}"</string>
    </array>

    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>${STATE_DIR}/logs/launchd_server.out.log</string>
    <key>StandardErrorPath</key>
    <string>${STATE_DIR}/logs/launchd_server.err.log</string>
  </dict>
</plist>
PLIST

cat >"${PLIST_FRONTEND_PATH}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>${PLIST_FRONTEND_ID}</string>

    <key>ProgramArguments</key>
    <array>
      <string>/bin/zsh</string>
      <string>-lc</string>
      <string>cd "${ROOT_DIR}/frontend" &amp;&amp; exec env NEXT_DISABLE_TURBOPACK=1 PORT="${FRONTEND_PORT}" npx next dev -p "${FRONTEND_PORT}"</string>
    </array>

    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>${STATE_DIR}/logs/launchd_frontend.out.log</string>
    <key>StandardErrorPath</key>
    <string>${STATE_DIR}/logs/launchd_frontend.err.log</string>
  </dict>
</plist>
PLIST

launchctl unload "${PLIST_SERVER_PATH}" >/dev/null 2>&1 || true
launchctl unload "${PLIST_FRONTEND_PATH}" >/dev/null 2>&1 || true

launchctl load "${PLIST_SERVER_PATH}"
launchctl load "${PLIST_FRONTEND_PATH}"

echo "✓ Installed LaunchAgents (autostart)"
echo "  - ${PLIST_SERVER_PATH}"
echo "  - ${PLIST_FRONTEND_PATH}"
echo "  Backend:  http://${HOST}:${PORT}"
echo "  Frontend: http://127.0.0.1:${FRONTEND_PORT}"
echo "  Logs:"
echo "   - ${STATE_DIR}/logs/launchd_server.out.log"
echo "   - ${STATE_DIR}/logs/launchd_server.err.log"
echo "   - ${STATE_DIR}/logs/launchd_frontend.out.log"
echo "   - ${STATE_DIR}/logs/launchd_frontend.err.log"

