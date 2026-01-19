#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PLIST_ID="com.vn-bond-lab.ingest"
PLIST_PATH="${HOME}/Library/LaunchAgents/${PLIST_ID}.plist"
STATE_DIR="${STATE_DIR:-${HOME}/Library/Application Support/vn-bond-lab}"

mkdir -p "${HOME}/Library/LaunchAgents"
mkdir -p "${STATE_DIR}/logs"

# NOTE: Some macOS configurations (notably iCloud Drive paths) may block
# LaunchAgents from writing/executing inside iCloud Drive (Operation not permitted).
# We avoid that by:
# - Running the Python module directly (no ./scripts/*.sh)
# - Writing DB/logs into a writable state dir (default: ~/Library/Application Support/vn-bond-lab)

PY_BIN="${PY_BIN:-}"
if [[ -z "${PY_BIN}" ]]; then
  if command -v python3.11 >/dev/null 2>&1; then
    PY_BIN="$(command -v python3.11)"
  else
    PY_BIN="$(command -v python3)"
  fi
fi

DB_PATH="${DB_PATH:-${STATE_DIR}/bonds.duckdb}"
RAW_DATA_PATH="${RAW_DATA_PATH:-${STATE_DIR}/raw}"

# Default: run once per day (local time). Override with:
#   DAILY_TIME=18:05 ./scripts/install_launchagent_macos.sh
DAILY_TIME="${DAILY_TIME:-18:05}"
HOUR="${DAILY_TIME%:*}"
MINUTE="${DAILY_TIME#*:}"
HOUR="$((10#${HOUR}))"
MINUTE="$((10#${MINUTE}))"

# Default providers: all daily-capable official sources.
# Override with:
#   PROVIDERS="sbv_interbank sbv_policy hnx_trading" ./scripts/install_launchagent_macos.sh
PROVIDERS="${PROVIDERS:-hnx_yield_curve hnx_ftp_pdf hnx_auction hnx_trading sbv_interbank sbv_policy fred_global lai_suat_rates}"

# Run at load is safe because we use a once-per-day stamp to prevent duplicates.
RUN_AT_LOAD="${RUN_AT_LOAD:-true}"

cat >"${PLIST_PATH}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>${PLIST_ID}</string>

    <key>ProgramArguments</key>
    <array>
      <string>/bin/zsh</string>
      <string>-lc</string>
      <string>mkdir -p "${STATE_DIR}/logs" "${RAW_DATA_PATH}" &amp;&amp; cd "${STATE_DIR}" &amp;&amp; STAMP="${STATE_DIR}/last_success_\$(/bin/date +%F)" &amp;&amp; if [[ -f "\$STAMP" ]]; then exit 0; fi &amp;&amp; (curl -fsS http://127.0.0.1:8001/healthz >/dev/null 2&gt;&amp;1 &amp;&amp; curl -fsS -X POST http://127.0.0.1:8001/api/admin/ingest/daily >/dev/null 2&gt;&amp;1 || env PYTHONPATH="${ROOT_DIR}" DB_PATH="${DB_PATH}" RAW_DATA_PATH="${RAW_DATA_PATH}" DEMO_MODE=false LOG_LEVEL=INFO "${PY_BIN}" -m app.ingest daily --providers ${PROVIDERS}) &gt;&gt; "${STATE_DIR}/logs/local_ingest.log" 2&gt;&amp;1 &amp;&amp; touch "\$STAMP"</string>
    </array>

    <key>RunAtLoad</key>
    <${RUN_AT_LOAD}/>
    <key>StartCalendarInterval</key>
    <dict>
      <key>Hour</key><integer>${HOUR}</integer>
      <key>Minute</key><integer>${MINUTE}</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>${STATE_DIR}/logs/launchd_ingest.out.log</string>
    <key>StandardErrorPath</key>
    <string>${STATE_DIR}/logs/launchd_ingest.err.log</string>
  </dict>
</plist>
PLIST

launchctl unload "${PLIST_PATH}" >/dev/null 2>&1 || true
launchctl load "${PLIST_PATH}"

echo "✓ Installed LaunchAgent: ${PLIST_PATH}"
echo "  State dir: ${STATE_DIR}"
echo "  DB: ${DB_PATH}"
echo "  Raw: ${RAW_DATA_PATH}"
echo "  Daily time: ${DAILY_TIME}"
echo "  Providers: ${PROVIDERS}"
echo "  Logs:"
echo "   - ${STATE_DIR}/logs/local_ingest.log"
echo "   - ${STATE_DIR}/logs/launchd_ingest.out.log"
echo "   - ${STATE_DIR}/logs/launchd_ingest.err.log"
