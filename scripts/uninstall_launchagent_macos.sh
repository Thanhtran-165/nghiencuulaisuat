#!/bin/bash
set -euo pipefail

PLIST_ID="com.vn-bond-lab.ingest"
PLIST_PATH="${HOME}/Library/LaunchAgents/${PLIST_ID}.plist"

if [[ -f "${PLIST_PATH}" ]]; then
  launchctl unload "${PLIST_PATH}" >/dev/null 2>&1 || true
  rm -f "${PLIST_PATH}"
  echo "✓ Uninstalled LaunchAgent: ${PLIST_PATH}"
else
  echo "No LaunchAgent found at: ${PLIST_PATH}"
fi
