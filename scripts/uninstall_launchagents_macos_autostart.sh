#!/bin/bash
set -euo pipefail

PLIST_SERVER_ID="com.vn-bond-lab.server"
PLIST_FRONTEND_ID="com.vn-bond-lab.frontend"
PLIST_LOCAL_ID="com.vn-bond-lab.local"

for id in "${PLIST_SERVER_ID}" "${PLIST_FRONTEND_ID}" "${PLIST_LOCAL_ID}"; do
  path="${HOME}/Library/LaunchAgents/${id}.plist"
  if [[ -f "${path}" ]]; then
    launchctl unload "${path}" >/dev/null 2>&1 || true
    rm -f "${path}"
    echo "✓ Uninstalled: ${path}"
  fi
done

