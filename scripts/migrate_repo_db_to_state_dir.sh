#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

STATE_DIR="${STATE_DIR:-}"
if [[ -z "${STATE_DIR}" ]]; then
  STATE_DIR="${HOME}/Library/Application Support/vn-bond-lab"
fi

SRC_DB="${SRC_DB:-$ROOT_DIR/.local-data/bonds.duckdb}"
DST_DB="${DST_DB:-${STATE_DIR}/bonds.duckdb}"

ts() { date '+%Y-%m-%dT%H:%M:%S%z'; }

if [[ ! -f "$SRC_DB" ]]; then
  echo "[$(ts)] ERROR: source DB not found: $SRC_DB" >&2
  exit 1
fi

mkdir -p "${STATE_DIR}/backups" "${STATE_DIR}/logs" "${STATE_DIR}/raw" "${STATE_DIR}/pids"

echo "[$(ts)] Migrating repo DB -> STATE_DIR"
echo "  SRC_DB=$SRC_DB"
echo "  DST_DB=$DST_DB"

UID_NUM="$(id -u)"
SERVER_PLIST="${HOME}/Library/LaunchAgents/com.vn-bond-lab.server.plist"
FRONTEND_PLIST="${HOME}/Library/LaunchAgents/com.vn-bond-lab.frontend.plist"

echo "[$(ts)] Stopping local services (to avoid DuckDB locks)..."
# Stop manually-started processes (scripts PID files / lsof fallback).
./scripts/stop_local_all.sh >/dev/null 2>&1 || true
# If LaunchAgents are loaded (KeepAlive), temporarily boot them out.
if launchctl list | grep -q "com.vn-bond-lab.server"; then
  launchctl bootout "gui/${UID_NUM}" "$SERVER_PLIST" >/dev/null 2>&1 || true
fi
if launchctl list | grep -q "com.vn-bond-lab.frontend"; then
  launchctl bootout "gui/${UID_NUM}" "$FRONTEND_PLIST" >/dev/null 2>&1 || true
fi
sleep 0.5

backup=""
if [[ -f "$DST_DB" ]]; then
  backup="${STATE_DIR}/backups/bonds_$(date '+%Y%m%d_%H%M%S').duckdb"
  echo "[$(ts)] Backing up existing DST_DB -> $backup"
  cp -f "$DST_DB" "$backup"
  if [[ -f "${DST_DB}.wal" ]]; then
    cp -f "${DST_DB}.wal" "${backup}.wal" || true
  fi
fi

echo "[$(ts)] Copying DB..."
cp -f "$SRC_DB" "$DST_DB"
if [[ -f "${SRC_DB}.wal" ]]; then
  cp -f "${SRC_DB}.wal" "${DST_DB}.wal" || true
fi

if [[ -n "${backup}" && -f "${backup}" ]]; then
  echo "[$(ts)] Merging newer rows from previous DST backup into new DST_DB..."
  python3.11 - <<PY
from pathlib import Path
import duckdb

dst = Path("${DST_DB}")
bak = Path("${backup}")

con = duckdb.connect(str(dst))
con.execute(f"ATTACH '{bak.as_posix()}' AS bak")

def merge_sql(table: str, cols: list[str], conflict: str, updates: dict[str, str]):
    col_list = ", ".join([f'"{c}"' for c in cols])
    upd_list = ", ".join([f'{k} = {v}' for k, v in updates.items()])
    before = con.execute(f"SELECT COUNT(*)::BIGINT FROM {table}").fetchone()[0]
    con.execute(
        f"""
        INSERT INTO {table} ({col_list})
        SELECT {col_list} FROM bak.{table}
        ON CONFLICT {conflict}
        DO UPDATE SET {upd_list}
        """
    )
    after = con.execute(f"SELECT COUNT(*)::BIGINT FROM {table}").fetchone()[0]
    print(table, "rows_before", int(before), "rows_after", int(after))

def merge_do_nothing(table: str, cols: list[str], conflict: str):
    col_list = ", ".join([f'"{c}"' for c in cols])
    before = con.execute(f"SELECT COUNT(*)::BIGINT FROM {table}").fetchone()[0]
    con.execute(
        f"""
        INSERT INTO {table} ({col_list})
        SELECT {col_list} FROM bak.{table}
        ON CONFLICT {conflict}
        DO NOTHING
        """
    )
    after = con.execute(f"SELECT COUNT(*)::BIGINT FROM {table}").fetchone()[0]
    print(table, "rows_before", int(before), "rows_after", int(after))

def cols_for(table: str) -> list[str]:
    return [r[1] for r in con.execute(f"PRAGMA table_info('{table}')").fetchall()]

try:
    # Raw/primary datasets: keep union; if duplicates exist, prefer latest values from backup.
    merge_sql(
        "gov_yield_curve",
        cols_for("gov_yield_curve"),
        "(date, tenor_label, source)",
        {
            "tenor_days": "EXCLUDED.tenor_days",
            "spot_rate_continuous": "EXCLUDED.spot_rate_continuous",
            "par_yield": "EXCLUDED.par_yield",
            "spot_rate_annual": "EXCLUDED.spot_rate_annual",
            "raw_file": "EXCLUDED.raw_file",
            "fetched_at": "EXCLUDED.fetched_at",
        },
    )
except Exception as e:
    print("merge_skip gov_yield_curve", e)

try:
    merge_sql(
        "interbank_rates",
        cols_for("interbank_rates"),
        "(date, tenor_label, source)",
        {
            "rate": "EXCLUDED.rate",
            "raw_file": "EXCLUDED.raw_file",
            "fetched_at": "EXCLUDED.fetched_at",
        },
    )
except Exception as e:
    print("merge_skip interbank_rates", e)

try:
    merge_sql(
        "gov_secondary_trading",
        cols_for("gov_secondary_trading"),
        "(date, segment, bucket_label, source)",
        {
            "segment_kind": "EXCLUDED.segment_kind",
            "segment_code": "EXCLUDED.segment_code",
            "bucket_kind": "EXCLUDED.bucket_kind",
            "bucket_code": "EXCLUDED.bucket_code",
            "bucket_display": "EXCLUDED.bucket_display",
            "volume": "EXCLUDED.volume",
            "value": "EXCLUDED.value",
            "avg_yield": "EXCLUDED.avg_yield",
            "raw_file": "EXCLUDED.raw_file",
            "fetched_at": "EXCLUDED.fetched_at",
        },
    )
except Exception as e:
    print("merge_skip gov_secondary_trading", e)

try:
    merge_sql(
        "gov_auction_results",
        cols_for("gov_auction_results"),
        "(date, instrument_type, tenor_label, source)",
        {
            "tenor_days": "EXCLUDED.tenor_days",
            "amount_offered": "EXCLUDED.amount_offered",
            "amount_sold": "EXCLUDED.amount_sold",
            "bid_to_cover": "EXCLUDED.bid_to_cover",
            "cut_off_yield": "EXCLUDED.cut_off_yield",
            "avg_yield": "EXCLUDED.avg_yield",
            "raw_file": "EXCLUDED.raw_file",
            "fetched_at": "EXCLUDED.fetched_at",
        },
    )
except Exception as e:
    print("merge_skip gov_auction_results", e)

try:
    merge_sql(
        "policy_rates",
        cols_for("policy_rates"),
        "(date, rate_name, source)",
        {
            "rate": "EXCLUDED.rate",
            "raw_file": "EXCLUDED.raw_file",
            "fetched_at": "EXCLUDED.fetched_at",
        },
    )
except Exception as e:
    print("merge_skip policy_rates", e)

try:
    merge_sql(
        "global_rates_daily",
        cols_for("global_rates_daily"),
        "(date, series_id, source)",
        {
            "series_name": "EXCLUDED.series_name",
            "value": "EXCLUDED.value",
            "fetched_at": "EXCLUDED.fetched_at",
        },
    )
except Exception as e:
    print("merge_skip global_rates_daily", e)

try:
    # bank_rates may have frequent re-scrapes; keep latest snapshot.
    merge_sql(
        "bank_rates",
        cols_for("bank_rates"),
        "(date, series_code, bank_name, term_months)",
        {
            "product_group": "EXCLUDED.product_group",
            "term_label": "EXCLUDED.term_label",
            "rate_min_pct": "EXCLUDED.rate_min_pct",
            "rate_max_pct": "EXCLUDED.rate_max_pct",
            "rate_pct": "EXCLUDED.rate_pct",
            "source_url": "EXCLUDED.source_url",
            "source_priority": "EXCLUDED.source_priority",
            "scraped_at": "EXCLUDED.scraped_at",
            "fetched_at": "EXCLUDED.fetched_at",
            "source": "EXCLUDED.source",
        },
    )
except Exception as e:
    print("merge_skip bank_rates", e)

con.execute("DETACH bak")
con.close()
print("merge_done")
PY
fi

echo "[$(ts)] Starting local services..."
./scripts/run_local_all.sh >/dev/null 2>&1 || true

# Re-enable LaunchAgents if they exist (optional).
if [[ -f "$SERVER_PLIST" ]]; then
  launchctl bootstrap "gui/${UID_NUM}" "$SERVER_PLIST" >/dev/null 2>&1 || true
fi
if [[ -f "$FRONTEND_PLIST" ]]; then
  launchctl bootstrap "gui/${UID_NUM}" "$FRONTEND_PLIST" >/dev/null 2>&1 || true
fi

echo "[$(ts)] Done."
echo "  UI:      http://127.0.0.1:3002"
echo "  Backend: http://127.0.0.1:8001"
