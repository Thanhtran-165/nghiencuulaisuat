#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8001}"
START_DATE="${START_DATE:-1900-01-01}"
END_DATE="${END_DATE:-2100-12-31}"
MAX_DATES_PER_BATCH="${MAX_DATES_PER_BATCH:-300}"
SLEEP_SECONDS="${SLEEP_SECONDS:-0}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found; required to parse JSON." >&2
  exit 1
fi

echo "[backfill-stress] base_url=$BASE_URL start=$START_DATE end=$END_DATE batch=$MAX_DATES_PER_BATCH sleep=$SLEEP_SECONDS"

curl -fsS --connect-timeout 3 --max-time 30 "$BASE_URL/healthz" >/dev/null || {
  echo "[backfill-stress] server not reachable at $BASE_URL (healthz failed)" >&2
  exit 1
}

while true; do
  payload=""
  if ! payload="$(curl -fsS --retry 5 --retry-all-errors --retry-delay 1 --connect-timeout 3 --max-time 1800 -X POST \
    "$BASE_URL/api/admin/stress/compute-range?start_date=$START_DATE&end_date=$END_DATE&max_dates=$MAX_DATES_PER_BATCH&skip_existing=true"
  )"; then
    echo "[$(date '+%F %T')] request failed; retrying..." >&2
    sleep 2
    continue
  fi

  if [[ -z "${payload//[[:space:]]/}" ]]; then
    echo "[$(date '+%F %T')] empty response; retrying..." >&2
    sleep 2
    continue
  fi

  parsed=""
  if ! parsed="$(python3 -c 'import json,sys; data=json.load(sys.stdin); print(int(data.get("total_candidate_dates",0)), int(data.get("pending_dates",0)), int(data.get("processed",0)), int(data.get("succeeded",0)), int(data.get("skipped",0)), int(data.get("failed",0)), int(data.get("remaining",0)))' <<<"$payload")"; then
    echo "[$(date '+%F %T')] invalid JSON response (first 200 bytes):" >&2
    echo "${payload:0:200}" >&2
    sleep 2
    continue
  fi

  total="$(awk '{print $1}' <<<"$parsed")"
  pending="$(awk '{print $2}' <<<"$parsed")"
  processed="$(awk '{print $3}' <<<"$parsed")"
  succeeded="$(awk '{print $4}' <<<"$parsed")"
  skipped="$(awk '{print $5}' <<<"$parsed")"
  failed="$(awk '{print $6}' <<<"$parsed")"
  remaining="$(awk '{print $7}' <<<"$parsed")"

  echo "[$(date '+%F %T')] processed=$processed ok=$succeeded skip=$skipped fail=$failed pending=$pending remaining=$remaining total_candidates=$total"

  if [[ "$pending" -le 0 || "$processed" -le 0 || "$remaining" -le 0 ]]; then
    echo "[backfill-stress] done"
    break
  fi

  if [[ "$SLEEP_SECONDS" != "0" ]]; then
    sleep "$SLEEP_SECONDS"
  fi
done

