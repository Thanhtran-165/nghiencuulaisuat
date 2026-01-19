"""
FastAPI routes for data access
"""
import logging
import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional
from io import StringIO

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.db.schema import DatabaseManager, db_manager as default_db_manager

logger = logging.getLogger(__name__)

# Database manager is injected by app startup, but default to a lightweight
# in-memory singleton to keep endpoints test-friendly.
db_manager: DatabaseManager = default_db_manager


def set_db_manager(manager: DatabaseManager) -> None:
    global db_manager
    db_manager = manager


# Create router
router = APIRouter()

# Health, Readiness, and Metrics endpoints (public, no auth)
@router.get("/healthz")
async def healthz():
    """Quick health check (no DB query) - for load balancers"""
    try:
        from app.observability import get_health_status
        return get_health_status()
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@router.get("/readyz")
async def readyz():
    """Readiness check (includes DB and schema verification)"""
    try:
        from app.observability import get_readiness_status
        return get_readiness_status(db_manager)
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail="Service not ready")

@router.get("/metrics")
async def metrics():
    """Prometheus-style metrics exposition"""
    try:
        from app.observability import metrics_registry
        from fastapi.responses import Response
        metrics_text = metrics_registry.format_prometheus()
        return Response(
            content=metrics_text,
            media_type="text/plain"
        )
    except Exception as e:
        logger.error(f"Metrics export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Version endpoint (public)
@router.get("/api/version")
async def get_version():
    """Get version and feature information"""
    try:
        from app.version import get_version_info
        return get_version_info()
    except Exception as e:
        logger.error(f"Error getting version: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class DatasetStats(BaseModel):
    rows: int
    min_date: Optional[str] = None
    max_date: Optional[str] = None


class DatasetCatalogItem(BaseModel):
    id: str
    name: str
    description: str
    provider: str
    url: str
    access_method: str
    supports_historical: bool
    earliest_known_date: Optional[str] = None
    accumulation_start: Optional[str] = None
    provenance: str
    table: str
    frequency: str
    stats: Optional[DatasetStats] = None


class DatasetCatalogResponse(BaseModel):
    catalog_date: str
    datasets: List[DatasetCatalogItem]


class DatasetDetailResponse(BaseModel):
    dataset: DatasetCatalogItem
    columns: list[dict]
    sample: list[dict]


def _safe_table_stats(table: str) -> Optional[dict]:
    """
    Return lightweight table stats: rows + optional min/max(date) if column exists.
    This endpoint is UI-facing (Next.js), so we prefer best-effort instead of hard failure.
    """
    try:
        if not db_manager.con:
            return None
        cols = [r[1] for r in db_manager.con.execute(f"PRAGMA table_info('{table}')").fetchall()]
        has_date = "date" in cols
        if has_date:
            row = db_manager.con.execute(
                f"SELECT COUNT(*)::BIGINT AS rows, MIN(date)::VARCHAR AS min_date, MAX(date)::VARCHAR AS max_date FROM {table}"
            ).fetchone()
            return {"rows": int(row[0]), "min_date": row[1], "max_date": row[2]}
        row = db_manager.con.execute(f"SELECT COUNT(*)::BIGINT AS rows FROM {table}").fetchone()
        return {"rows": int(row[0])}
    except Exception:
        return None


@router.get("/api/data/catalog", response_model=DatasetCatalogResponse)
async def get_data_catalog():
    """Return dataset catalog metadata + basic table stats for the Next.js Data tab."""
    try:
        from datetime import date as dt_date
        from app.dataset_catalog import DATASET_CATALOG

        datasets: list[DatasetCatalogItem] = []
        for dataset_id, info in DATASET_CATALOG.items():
            stats = _safe_table_stats(info.get("table"))
            datasets.append(
                DatasetCatalogItem(
                    id=dataset_id,
                    name=info.get("name"),
                    description=info.get("description"),
                    provider=info.get("provider"),
                    url=info.get("url"),
                    access_method=info.get("access_method"),
                    supports_historical=bool(info.get("supports_historical")),
                    earliest_known_date=info.get("earliest_known_date"),
                    accumulation_start=info.get("accumulation_start"),
                    provenance=info.get("provenance"),
                    table=info.get("table"),
                    frequency=info.get("frequency"),
                    stats=DatasetStats(**stats) if stats else None,
                )
            )

        datasets.sort(key=lambda d: d.id)
        return DatasetCatalogResponse(catalog_date=dt_date.today().isoformat(), datasets=datasets)
    except Exception as e:
        logger.error(f"Error building data catalog: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/data/{dataset_id}", response_model=DatasetDetailResponse)
async def get_data_dataset(dataset_id: str, limit: int = Query(50, ge=1, le=500)):
    """Return a dataset detail: metadata, schema, and a small sample."""
    try:
        from app.dataset_catalog import DATASET_CATALOG

        if dataset_id not in DATASET_CATALOG:
            raise HTTPException(status_code=404, detail="Unknown dataset_id")
        info = DATASET_CATALOG[dataset_id]
        table = info.get("table")

        stats = _safe_table_stats(table)
        item = DatasetCatalogItem(
            id=dataset_id,
            name=info.get("name"),
            description=info.get("description"),
            provider=info.get("provider"),
            url=info.get("url"),
            access_method=info.get("access_method"),
            supports_historical=bool(info.get("supports_historical")),
            earliest_known_date=info.get("earliest_known_date"),
            accumulation_start=info.get("accumulation_start"),
            provenance=info.get("provenance"),
            table=table,
            frequency=info.get("frequency"),
            stats=DatasetStats(**stats) if stats else None,
        )

        if not db_manager.con:
            return DatasetDetailResponse(dataset=item, columns=[], sample=[])

        cols = db_manager.con.execute(f"PRAGMA table_info('{table}')").fetchall()
        columns = [
            {"name": r[1], "type": r[2], "not_null": bool(r[3]), "default": r[4], "pk": bool(r[5])}
            for r in cols
        ]

        col_names = [c["name"] for c in columns]
        order_by = "date DESC" if "date" in col_names else None
        query = f"SELECT * FROM {table}"
        if order_by:
            query += f" ORDER BY {order_by}"
        query += f" LIMIT {int(limit)}"
        cur = db_manager.con.execute(query)
        sample_cols = [d[0] for d in (cur.description or [])]
        sample = [dict(zip(sample_cols, row)) for row in cur.fetchall()]

        return DatasetDetailResponse(dataset=item, columns=columns, sample=sample)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching dataset detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/insights/horizons")
async def get_insights_horizons():
    """
    Phase 1: "Nhận định 3 thời hạn" payload for the Insights UI.
    Uses observation-based horizons ("phiên"), primary-series readiness, and transparent fallbacks.
    """
    try:
        from app.analytics.horizon_assessment import HorizonAssessmentEngine

        engine = HorizonAssessmentEngine(db_manager)
        return engine.build_payload()
    except Exception as e:
        logger.error(f"Error building insights horizons payload: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Pydantic models for response
class YieldCurveRecord(BaseModel):
    date: date
    tenor_label: str
    tenor_days: int
    spot_rate_continuous: Optional[float]
    par_yield: Optional[float]
    spot_rate_annual: Optional[float]
    source: str
    fetched_at: datetime

class YieldCurveMetricsRecord(BaseModel):
    date: date
    y2: Optional[float] = None
    y5: Optional[float] = None
    y10: Optional[float] = None
    slope_10y_2y: Optional[float] = None
    curvature_2_5_10: Optional[float] = None
    source_2y: Optional[str] = None
    source_5y: Optional[str] = None
    source_10y: Optional[str] = None

class InterbankRateRecord(BaseModel):
    date: date
    tenor_label: str
    rate: float
    source: str
    fetched_at: datetime

class InterbankCompareRow(BaseModel):
    tenor_label: str
    today_rate: Optional[float] = None
    prev_rate: Optional[float] = None
    change_bps: Optional[float] = None
    today_source: Optional[str] = None
    prev_source: Optional[str] = None


class InterbankCompareResponse(BaseModel):
    today_date: Optional[date] = None
    prev_date: Optional[date] = None
    today_fetched_at: Optional[datetime] = None
    prev_fetched_at: Optional[datetime] = None
    rows: List[InterbankCompareRow]

class AuctionRecord(BaseModel):
    date: date
    instrument_type: str
    tenor_label: str
    tenor_days: int
    amount_offered: Optional[float]
    amount_sold: Optional[float]
    bid_to_cover: Optional[float]
    cut_off_yield: Optional[float]
    avg_yield: Optional[float]
    source: str
    raw_file: Optional[str]
    fetched_at: datetime

class SecondaryTradingRecord(BaseModel):
    date: date
    segment: str
    bucket_label: str
    segment_kind: Optional[str] = None
    segment_code: Optional[str] = None
    bucket_kind: Optional[str] = None
    bucket_code: Optional[str] = None
    bucket_display: Optional[str] = None
    volume: Optional[float]
    value: Optional[float]
    avg_yield: Optional[float]
    source: str
    raw_file: Optional[str]
    fetched_at: datetime

class PolicyRateRecord(BaseModel):
    date: date
    rate_name: str
    rate: float
    source: str
    raw_file: Optional[str]
    fetched_at: datetime

class IngestRunRecord(BaseModel):
    id: int
    provider: str
    start_date: Optional[date]
    end_date: Optional[date]
    status: str
    rows_inserted: int
    error_message: Optional[str]
    started_at: datetime
    ended_at: Optional[datetime]

class DashboardMetrics(BaseModel):
    two_y: Optional[float]
    five_y: Optional[float]
    ten_y: Optional[float]
    spread_10y_2y: Optional[float]
    yield_prev_date: Optional[str] = None
    two_y_prev: Optional[float] = None
    five_y_prev: Optional[float] = None
    ten_y_prev: Optional[float] = None
    spread_10y_2y_prev: Optional[float] = None
    two_y_change_bps: Optional[float] = None
    five_y_change_bps: Optional[float] = None
    ten_y_change_bps: Optional[float] = None
    spread_10y_2y_change_bps: Optional[float] = None
    on_rate: Optional[float]
    deposit_avg_12m: Optional[float] = None
    deposit_avg_12m_prev: Optional[float] = None
    deposit_change_bps: Optional[float] = None
    loan_avg: Optional[float] = None
    loan_avg_prev: Optional[float] = None
    loan_change_bps: Optional[float] = None
    bank_deposit_date: Optional[str] = None
    bank_deposit_prev_date: Optional[str] = None
    bank_loan_date: Optional[str] = None
    bank_loan_prev_date: Optional[str] = None
    stress_date: Optional[str] = None
    stress_index: Optional[float] = None
    stress_bucket: Optional[str] = None
    stress_prev_date: Optional[str] = None
    stress_prev_index: Optional[float] = None
    stress_change: Optional[float] = None
    latest_date: Optional[str]


# Yield curve endpoints
@router.get("/api/yield-curve/latest", response_model=List[YieldCurveRecord])
async def get_latest_yield_curve():
    """Get latest yield curve data"""
    try:
        records = db_manager.get_latest_yield_curve()
        return [YieldCurveRecord(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching latest yield curve: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/yield-curve", response_model=List[YieldCurveRecord])
async def get_yield_curve_by_date(
    date: str = Query(..., description="Date in YYYY-MM-DD format")
):
    """Get yield curve for a specific date"""
    try:
        records = db_manager.get_latest_yield_curve(date=date)
        if not records:
            raise HTTPException(status_code=404, detail="No data found for this date")
        return [YieldCurveRecord(**r) for r in records]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching yield curve for {date}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/yield-curve/range", response_model=List[YieldCurveRecord])
async def get_yield_curve_range(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
    tenor: Optional[str] = Query(None, description="Filter by tenor (e.g., 2Y, 5Y, 10Y)")
):
    """Get yield curve data for a date range"""
    try:
        # Build query
        conditions = ["date >= ?", "date <= ?"]
        params = [start_date, end_date]

        if tenor:
            conditions.append("tenor_label = ?")
            params.append(tenor)

        where_clause = "WHERE " + " AND ".join(conditions)

        sql = f"""
        SELECT * FROM gov_yield_curve
        {where_clause}
        ORDER BY date ASC, tenor_days
        """

        result = db_manager.con.execute(sql, params).fetchall()
        columns = [desc[0] for desc in db_manager.con.description]
        records = [dict(zip(columns, row)) for row in result]

        return [YieldCurveRecord(**r) for r in records]

    except Exception as e:
        logger.error(f"Error fetching yield curve range: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/yield-curve/metrics", response_model=List[YieldCurveMetricsRecord])
async def get_yield_curve_metrics(
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD format (optional)"),
    lookback: int = Query(180, ge=20, le=2000, description="Number of observations (phiên) to return"),
):
    """
    Compact daily yield-curve metrics for bond–bond analysis:
    - Level: 10Y
    - Slope: 10Y–2Y
    - Curvature: 2*5Y − (2Y+10Y)

    Notes:
    - Uses observation-based lookback ("phiên") instead of calendar days.
    - Canonicalizes per (date, tenor) using source priority: HNX/HNX_YC > ABO > others.
    """
    try:
        end_date_expr = (
            "?"
            if end_date
            else """
            COALESCE(
              (SELECT MAX(date) FROM gov_yield_curve WHERE source IN ('HNX_YC','HNX')),
              (SELECT MAX(date) FROM gov_yield_curve)
            )
            """
        )
        params: list = [end_date] if end_date else []

        sql = f"""
        WITH dates AS (
          SELECT DISTINCT date
          FROM gov_yield_curve
          WHERE date <= ({end_date_expr})
          ORDER BY date DESC
          LIMIT {int(lookback)}
        ),
        ranked AS (
          SELECT
            y.date,
            y.tenor_label,
            COALESCE(y.spot_rate_annual, y.par_yield) AS y,
            y.source,
            y.fetched_at,
            ROW_NUMBER() OVER (
              PARTITION BY y.date, y.tenor_label
              ORDER BY
                CASE
                  WHEN y.source IN ('HNX_YC','HNX') THEN 1
                  WHEN y.source = 'ABO' THEN 2
                  ELSE 9
                END ASC,
                y.fetched_at DESC
            ) AS rn
          FROM gov_yield_curve y
          WHERE y.date IN (SELECT date FROM dates)
            AND y.tenor_label IN ('2Y','5Y','10Y')
        ),
        canon AS (
          SELECT date, tenor_label, y, source
          FROM ranked
          WHERE rn = 1
        ),
        pvt AS (
          SELECT
            date,
            MAX(CASE WHEN tenor_label = '2Y' THEN y END) AS y2,
            MAX(CASE WHEN tenor_label = '5Y' THEN y END) AS y5,
            MAX(CASE WHEN tenor_label = '10Y' THEN y END) AS y10,
            MAX(CASE WHEN tenor_label = '2Y' THEN source END) AS source_2y,
            MAX(CASE WHEN tenor_label = '5Y' THEN source END) AS source_5y,
            MAX(CASE WHEN tenor_label = '10Y' THEN source END) AS source_10y
          FROM canon
          GROUP BY date
        )
        SELECT
          date,
          y2,
          y5,
          y10,
          CASE WHEN y10 IS NOT NULL AND y2 IS NOT NULL THEN y10 - y2 ELSE NULL END AS slope_10y_2y,
          CASE
            WHEN y10 IS NOT NULL AND y2 IS NOT NULL AND y5 IS NOT NULL
              THEN (2 * y5) - (y2 + y10)
            ELSE NULL
          END AS curvature_2_5_10,
          source_2y,
          source_5y,
          source_10y
        FROM pvt
        ORDER BY date ASC
        """

        rows = db_manager.con.execute(sql, params).fetchall()
        columns = [desc[0] for desc in db_manager.con.description]
        records = [dict(zip(columns, row)) for row in rows]
        return [YieldCurveMetricsRecord(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching yield curve metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Interbank rate endpoints
@router.get("/api/interbank/latest", response_model=List[InterbankRateRecord])
async def get_latest_interbank_rates():
    """Get latest interbank rates"""
    try:
        # Canonical latest snapshot: pick one source per (date, tenor) with preference.
        sql = """
        WITH latest_date AS (
          SELECT COALESCE(
            (SELECT MAX(date) FROM interbank_rates WHERE source = 'SBV'),
            (SELECT MAX(date) FROM interbank_rates)
          ) AS d
        ),
        base AS (
          SELECT *
          FROM interbank_rates
          WHERE date = (SELECT d FROM latest_date)
        ),
        ranked AS (
          SELECT
            date,
            tenor_label,
            rate,
            source,
            fetched_at,
            ROW_NUMBER() OVER (
              PARTITION BY tenor_label
              ORDER BY
                CASE
                  WHEN source = 'SBV' THEN 1
                  WHEN source = 'ABO' THEN 2
                  ELSE 9
                END ASC,
                fetched_at DESC
            ) AS rn
          FROM base
        )
        SELECT date, tenor_label, rate, source, fetched_at
        FROM ranked
        WHERE rn = 1
        ORDER BY tenor_label
        """
        result = db_manager.con.execute(sql).fetchall()
        columns = [desc[0] for desc in db_manager.con.description]
        records = [dict(zip(columns, row)) for row in result]
        return [InterbankRateRecord(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching latest interbank rates: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/interbank/compare", response_model=InterbankCompareResponse)
async def get_interbank_compare():
    """Get latest interbank rates and previous available day (for dashboard comparison)."""
    try:
        today_date = db_manager.con.execute(
            """
            SELECT COALESCE(
              (SELECT MAX(date) FROM interbank_rates WHERE source = 'SBV'),
              (SELECT MAX(date) FROM interbank_rates)
            )
            """
        ).fetchone()[0]
        if today_date is None:
            return InterbankCompareResponse(today_date=None, prev_date=None, rows=[])

        prev_date = db_manager.con.execute(
            "SELECT MAX(date) FROM interbank_rates WHERE date < ?",
            [str(today_date)],
        ).fetchone()[0]

        dates = [today_date]
        if prev_date is not None:
            dates.append(prev_date)

        placeholders = ",".join(["?"] * len(dates))
        sql = f"""
        WITH base AS (
          SELECT date, tenor_label, rate, source, fetched_at
          FROM interbank_rates
          WHERE date IN ({placeholders})
            AND rate IS NOT NULL
        ),
        ranked AS (
          SELECT
            date,
            tenor_label,
            rate,
            source,
            fetched_at,
            ROW_NUMBER() OVER (
              PARTITION BY date, tenor_label
              ORDER BY
                CASE
                  WHEN source = 'SBV' THEN 1
                  WHEN source = 'ABO' THEN 2
                  ELSE 9
                END ASC,
                fetched_at DESC
            ) AS rn
          FROM base
        )
        SELECT date, tenor_label, rate, source, fetched_at
        FROM ranked
        WHERE rn = 1
        """

        rows = db_manager.con.execute(sql, [str(d) for d in dates]).fetchall()
        today_map: dict[str, float] = {}
        prev_map: dict[str, float] = {}
        today_source_map: dict[str, str] = {}
        prev_source_map: dict[str, str] = {}
        today_fetched_at: Optional[datetime] = None
        prev_fetched_at: Optional[datetime] = None

        for d, tenor, rate, source, fetched_at in rows:
            if d == today_date:
                today_map[str(tenor)] = float(rate)
                if source is not None:
                    today_source_map[str(tenor)] = str(source)
                if fetched_at is not None:
                    today_fetched_at = fetched_at if today_fetched_at is None else max(today_fetched_at, fetched_at)
            elif prev_date is not None and d == prev_date:
                prev_map[str(tenor)] = float(rate)
                if source is not None:
                    prev_source_map[str(tenor)] = str(source)
                if fetched_at is not None:
                    prev_fetched_at = fetched_at if prev_fetched_at is None else max(prev_fetched_at, fetched_at)

        tenors = sorted(set(today_map.keys()) | set(prev_map.keys()))
        # Prefer a stable economic order for common tenors.
        order = {"ON": 0, "1D": 0, "1W": 1, "2W": 2, "1M": 3, "3M": 4, "6M": 5, "9M": 6, "1Y": 7}
        tenors.sort(key=lambda t: (order.get(t, 999), t))

        out_rows: list[InterbankCompareRow] = []
        for t in tenors:
            tr = today_map.get(t)
            pr = prev_map.get(t)
            cbps = None
            if tr is not None and pr is not None:
                cbps = (tr - pr) * 100.0
            out_rows.append(
                InterbankCompareRow(
                    tenor_label=t,
                    today_rate=tr,
                    prev_rate=pr,
                    change_bps=cbps,
                    today_source=today_source_map.get(t),
                    prev_source=prev_source_map.get(t),
                )
            )

        return InterbankCompareResponse(
            today_date=today_date,
            prev_date=prev_date,
            today_fetched_at=today_fetched_at,
            prev_fetched_at=prev_fetched_at,
            rows=out_rows,
        )
    except Exception as e:
        logger.error(f"Error fetching interbank compare: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/interbank/timeseries", response_model=List[InterbankRateRecord])
async def get_interbank_timeseries(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
    tenor: Optional[str] = Query(None, description="Filter by tenor (e.g., ON, 1W, 1M, 3M)")
):
    """Get interbank rate time series"""
    try:
        records = db_manager.get_interbank_rates(
            start_date=start_date,
            end_date=end_date,
            tenor=tenor
        )
        return [InterbankRateRecord(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching interbank timeseries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Dashboard endpoint
@router.get("/api/dashboard/metrics", response_model=DashboardMetrics)
async def get_dashboard_metrics():
    """Get dashboard summary metrics"""
    try:
        def bps_delta(now: Optional[float], prev: Optional[float]) -> Optional[float]:
            if now is None or prev is None:
                return None
            return (now - prev) * 100.0

        # Yield curve (HNX preferred)
        latest_yield = db_manager.get_latest_yield_curve()
        latest_date = str(latest_yield[0]["date"]) if latest_yield else None

        two_y = next((r["spot_rate_annual"] for r in latest_yield if r["tenor_label"] == "2Y"), None)
        five_y = next((r["spot_rate_annual"] for r in latest_yield if r["tenor_label"] == "5Y"), None)
        ten_y = next((r["spot_rate_annual"] for r in latest_yield if r["tenor_label"] == "10Y"), None)

        spread_10y_2y = None
        if ten_y is not None and two_y is not None:
            spread_10y_2y = ten_y - two_y

        prev_yield_date = None
        prev_yield = []
        if latest_date:
            hnx_max = db_manager.con.execute(
                """
                SELECT MAX(date)
                FROM gov_yield_curve
                WHERE source IN ('HNX_YC','HNX')
                """
            ).fetchone()[0]

            if hnx_max is not None and str(hnx_max) == latest_date:
                prev_yield_date = db_manager.con.execute(
                    """
                    SELECT MAX(date)
                    FROM gov_yield_curve
                    WHERE source IN ('HNX_YC','HNX')
                      AND date < ?
                    """,
                    [str(hnx_max)],
                ).fetchone()[0]
            else:
                prev_yield_date = db_manager.con.execute(
                    """
                    SELECT MAX(date)
                    FROM gov_yield_curve
                    WHERE date < ?
                    """,
                    [latest_date],
                ).fetchone()[0]

            if prev_yield_date is not None:
                prev_yield = db_manager.get_latest_yield_curve(date=str(prev_yield_date))

        two_y_prev = next((r["spot_rate_annual"] for r in prev_yield if r["tenor_label"] == "2Y"), None)
        five_y_prev = next((r["spot_rate_annual"] for r in prev_yield if r["tenor_label"] == "5Y"), None)
        ten_y_prev = next((r["spot_rate_annual"] for r in prev_yield if r["tenor_label"] == "10Y"), None)

        spread_10y_2y_prev = None
        if ten_y_prev is not None and two_y_prev is not None:
            spread_10y_2y_prev = ten_y_prev - two_y_prev

        # Interbank (today level only for dashboard summary; detailed compare is /api/interbank/compare)
        interbank_on = db_manager.get_interbank_rates(tenor="ON")
        on_rate = interbank_on[0]["rate"] if interbank_on else None

        # Bank rates averages (today + previous available observation)
        deposit_term_months = 12

        max_pr = int(getattr(settings, "lai_suat_max_source_priority", 1))

        deposit_date = db_manager.con.execute(
            """
            SELECT MAX(date)
            FROM bank_rates
            WHERE product_group = 'deposit'
              AND term_months = ?
              AND rate_pct IS NOT NULL
              AND ((source_priority IS NULL OR source_priority <= ?) OR (source_url IS NOT NULL AND source_url LIKE ?))
            """,
            [int(deposit_term_months), int(max_pr), "%timo.vn/%"],
        ).fetchone()[0]
        deposit_prev_date = None
        if deposit_date is not None:
            deposit_prev_date = db_manager.con.execute(
                """
                SELECT MAX(date)
                FROM bank_rates
                WHERE product_group = 'deposit'
                  AND term_months = ?
                  AND rate_pct IS NOT NULL
                  AND date < ?
                  AND ((source_priority IS NULL OR source_priority <= ?) OR (source_url IS NOT NULL AND source_url LIKE ?))
                """,
                [int(deposit_term_months), str(deposit_date), int(max_pr), "%timo.vn/%"],
            ).fetchone()[0]

        deposit_avg = None
        if deposit_date is not None:
            deposit_avg = db_manager.con.execute(
                """
                SELECT AVG(rate_pct) AS v
                FROM bank_rates
                WHERE date = ?
                  AND product_group = 'deposit'
                  AND term_months = ?
                  AND rate_pct IS NOT NULL
                  AND ((source_priority IS NULL OR source_priority <= ?) OR (source_url IS NOT NULL AND source_url LIKE ?))
                """,
                [str(deposit_date), int(deposit_term_months), int(max_pr), "%timo.vn/%"],
            ).fetchone()[0]
        deposit_avg_prev = None
        if deposit_prev_date is not None:
            deposit_avg_prev = db_manager.con.execute(
                """
                SELECT AVG(rate_pct) AS v
                FROM bank_rates
                WHERE date = ?
                  AND product_group = 'deposit'
                  AND term_months = ?
                  AND rate_pct IS NOT NULL
                  AND ((source_priority IS NULL OR source_priority <= ?) OR (source_url IS NOT NULL AND source_url LIKE ?))
                """,
                [str(deposit_prev_date), int(deposit_term_months), int(max_pr), "%timo.vn/%"],
            ).fetchone()[0]

        loan_date = db_manager.con.execute(
            """
            SELECT MAX(date)
            FROM bank_rates
            WHERE product_group = 'loan'
              AND (rate_min_pct IS NOT NULL OR rate_max_pct IS NOT NULL OR rate_pct IS NOT NULL)
              AND ((source_priority IS NULL OR source_priority <= ?) OR (source_url IS NOT NULL AND source_url LIKE ?))
            """
            ,
            [int(max_pr), "%timo.vn/%"],
        ).fetchone()[0]
        loan_prev_date = None
        if loan_date is not None:
            loan_prev_date = db_manager.con.execute(
                """
                SELECT MAX(date)
                FROM bank_rates
                WHERE product_group = 'loan'
                  AND (rate_min_pct IS NOT NULL OR rate_max_pct IS NOT NULL OR rate_pct IS NOT NULL)
                  AND date < ?
                  AND ((source_priority IS NULL OR source_priority <= ?) OR (source_url IS NOT NULL AND source_url LIKE ?))
                """,
                [str(loan_date), int(max_pr), "%timo.vn/%"],
            ).fetchone()[0]

        loan_avg = None
        if loan_date is not None:
            loan_avg = db_manager.con.execute(
                """
                SELECT AVG(
                  CASE
                    WHEN rate_min_pct IS NOT NULL AND rate_max_pct IS NOT NULL THEN (rate_min_pct + rate_max_pct) / 2.0
                    WHEN rate_min_pct IS NOT NULL THEN rate_min_pct
                    WHEN rate_pct IS NOT NULL THEN rate_pct
                    ELSE NULL
                  END
                ) AS v
                FROM bank_rates
                WHERE date = ?
                  AND product_group = 'loan'
                  AND ((source_priority IS NULL OR source_priority <= ?) OR (source_url IS NOT NULL AND source_url LIKE ?))
                """,
                [str(loan_date), int(max_pr), "%timo.vn/%"],
            ).fetchone()[0]

        loan_avg_prev = None
        if loan_prev_date is not None:
            loan_avg_prev = db_manager.con.execute(
                """
                SELECT AVG(
                  CASE
                    WHEN rate_min_pct IS NOT NULL AND rate_max_pct IS NOT NULL THEN (rate_min_pct + rate_max_pct) / 2.0
                    WHEN rate_min_pct IS NOT NULL THEN rate_min_pct
                    WHEN rate_pct IS NOT NULL THEN rate_pct
                    ELSE NULL
                  END
                ) AS v
                FROM bank_rates
                WHERE date = ?
                  AND product_group = 'loan'
                  AND ((source_priority IS NULL OR source_priority <= ?) OR (source_url IS NOT NULL AND source_url LIKE ?))
                """,
                [str(loan_prev_date), int(max_pr), "%timo.vn/%"],
            ).fetchone()[0]

        deposit_avg_12m = float(deposit_avg) if deposit_avg is not None else None
        deposit_avg_12m_prev = float(deposit_avg_prev) if deposit_avg_prev is not None else None
        loan_avg_v = float(loan_avg) if loan_avg is not None else None
        loan_avg_prev_v = float(loan_avg_prev) if loan_avg_prev is not None else None

        deposit_change_bps = bps_delta(deposit_avg_12m, deposit_avg_12m_prev)
        loan_change_bps = bps_delta(loan_avg_v, loan_avg_prev_v)

        # Stress (latest + prev)
        stress_rows = db_manager.get_bondy_stress(limit=2)
        stress_latest = stress_rows[0] if len(stress_rows) >= 1 else None
        stress_prev = stress_rows[1] if len(stress_rows) >= 2 else None

        stress_index = None
        stress_bucket = None
        stress_date = None
        stress_prev_index = None
        stress_prev_date = None
        stress_change = None

        if stress_latest is not None:
            stress_date = str(stress_latest.get("date")) if stress_latest.get("date") else None
            stress_index = stress_latest.get("stress_index")
            stress_bucket = stress_latest.get("regime_bucket")
        if stress_prev is not None:
            stress_prev_date = str(stress_prev.get("date")) if stress_prev.get("date") else None
            stress_prev_index = stress_prev.get("stress_index")
        if stress_index is not None and stress_prev_index is not None:
            stress_change = float(stress_index) - float(stress_prev_index)

        return DashboardMetrics(
            two_y=two_y,
            five_y=five_y,
            ten_y=ten_y,
            spread_10y_2y=spread_10y_2y,
            yield_prev_date=str(prev_yield_date) if prev_yield_date is not None else None,
            two_y_prev=two_y_prev,
            five_y_prev=five_y_prev,
            ten_y_prev=ten_y_prev,
            spread_10y_2y_prev=spread_10y_2y_prev,
            two_y_change_bps=bps_delta(two_y, two_y_prev),
            five_y_change_bps=bps_delta(five_y, five_y_prev),
            ten_y_change_bps=bps_delta(ten_y, ten_y_prev),
            spread_10y_2y_change_bps=bps_delta(spread_10y_2y, spread_10y_2y_prev),
            on_rate=on_rate,
            deposit_avg_12m=deposit_avg_12m,
            deposit_avg_12m_prev=deposit_avg_12m_prev,
            deposit_change_bps=deposit_change_bps,
            loan_avg=loan_avg_v,
            loan_avg_prev=loan_avg_prev_v,
            loan_change_bps=loan_change_bps,
            bank_deposit_date=str(deposit_date) if deposit_date is not None else None,
            bank_deposit_prev_date=str(deposit_prev_date) if deposit_prev_date is not None else None,
            bank_loan_date=str(loan_date) if loan_date is not None else None,
            bank_loan_prev_date=str(loan_prev_date) if loan_prev_date is not None else None,
            stress_date=stress_date,
            stress_index=stress_index,
            stress_bucket=stress_bucket,
            stress_prev_date=stress_prev_date,
            stress_prev_index=stress_prev_index,
            stress_change=stress_change,
            latest_date=latest_date,
        )

    except Exception as e:
        logger.error(f"Error fetching dashboard metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Ingest runs endpoint
@router.get("/api/admin/ingest-runs", response_model=List[IngestRunRecord])
async def get_ingest_runs(
    limit: int = Query(100, description="Number of recent runs to return")
):
    """Get recent ingestion runs"""
    try:
        records = db_manager.get_ingest_runs(limit=limit)
        return [IngestRunRecord(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching ingest runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Admin endpoint to trigger ingestion
@router.post("/api/admin/ingest/daily")
async def trigger_daily_ingest(
    providers: Optional[List[str]] = Query(
        None,
        description="Optional provider allowlist. Default runs daily-capable official providers.",
    )
):
    """Trigger daily ingestion manually"""
    from app.ingest import IngestionPipeline

    try:
        # Run in background (for now, run synchronously)
        pipeline = IngestionPipeline(db_manager=db_manager)
        selected = providers or list(getattr(pipeline, "DEFAULT_DAILY_PROVIDERS", []))
        # Validate provider names to avoid surprises / typos.
        selected = [p for p in selected if p in getattr(pipeline, "PROVIDERS", {})]
        results = pipeline.run_daily(providers=selected)

        return {"status": "completed", "providers": selected, "results": results}
    except Exception as e:
        logger.error(f"Error triggering daily ingestion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/ingest/backfill")
async def trigger_backfill(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
    providers: Optional[List[str]] = Query(None, description="Providers to run")
):
    """Trigger backfill"""
    from app.ingest import IngestionPipeline

    try:
        pipeline = IngestionPipeline(db_manager=db_manager)
        results = pipeline.run_backfill(
            start_date=start_date,
            end_date=end_date,
            providers=providers
        )

        return {"status": "completed", "results": results}
    except Exception as e:
        logger.error(f"Error triggering backfill: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/admin/provider-status")
async def get_provider_status():
    """Get provider capability status from probe report"""
    import json
    from pathlib import Path

    probe_file = Path("reports/provider_probe.json")

    if not probe_file.exists():
        return {
            "status": "no_probe_data",
            "message": "No probe data available. Run 'python -m app.ingest probe' first.",
            "providers": {}
        }

    try:
        with open(probe_file, 'r') as f:
            probe_data = json.load(f)

        # Return simplified provider status for UI
        provider_status = {}
        for provider_name, provider_info in probe_data.get('providers', {}).items():
            provider_status[provider_name] = {
                'fetch_latest': provider_info['capabilities']['fetch_latest'],
                'fetch_historical': provider_info['capabilities']['fetch_historical'],
                'backfill_supported': provider_info['capabilities']['backfill_supported'],
                'earliest_success_date': provider_info.get('earliest_success_date'),
                'latest_success_date': provider_info.get('latest_success_date'),
                'failure_modes': provider_info.get('failure_modes', [])
            }

        return {
            "status": "ok",
            "probe_timestamp": probe_data.get('probe_timestamp'),
            "providers": provider_status
        }

    except Exception as e:
        logger.error(f"Error reading probe data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/ingest/probe")
async def trigger_probe():
    """Trigger provider probe"""
    from app.ingest import IngestionPipeline

    try:
        with IngestionPipeline() as pipeline:
            results = pipeline.run_probe()

        return {"status": "completed", "results": results}
    except Exception as e:
        logger.error(f"Error triggering probe: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Auction endpoints
@router.get("/api/auctions/latest", response_model=List[AuctionRecord])
async def get_latest_auctions(
    limit: int = Query(100, description="Number of recent auctions to return")
):
    """Get latest auction results"""
    try:
        sql = """
        SELECT * FROM gov_auction_results
        ORDER BY date DESC
        LIMIT ?
        """

        result = db_manager.con.execute(sql, [limit]).fetchall()
        columns = [desc[0] for desc in db_manager.con.description]
        records = [dict(zip(columns, row)) for row in result]

        return [AuctionRecord(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching latest auctions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/auctions/range", response_model=List[AuctionRecord])
async def get_auctions_range(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
    instrument_type: Optional[str] = Query(None, description="Filter by instrument type"),
    tenor: Optional[str] = Query(None, description="Filter by tenor (e.g., 5Y, 10Y)")
):
    """Get auction results for a date range"""
    try:
        conditions = ["date >= ?", "date <= ?"]
        params = [start_date, end_date]

        if instrument_type:
            conditions.append("instrument_type = ?")
            params.append(instrument_type)

        if tenor:
            conditions.append("tenor_label = ?")
            params.append(tenor)

        where_clause = "WHERE " + " AND ".join(conditions)

        sql = f"""
        SELECT * FROM gov_auction_results
        {where_clause}
        ORDER BY date DESC
        """

        result = db_manager.con.execute(sql, params).fetchall()
        columns = [desc[0] for desc in db_manager.con.description]
        records = [dict(zip(columns, row)) for row in result]

        return [AuctionRecord(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching auctions range: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/export/auctions.csv")
async def export_auctions_csv(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format")
):
    """Export auction results as CSV"""
    try:
        records = await get_auctions_range(start_date, end_date, instrument_type=None, tenor=None)

        # Create CSV
        output = StringIO()
        output.write("date,instrument_type,tenor_label,tenor_days,amount_offered,amount_sold,bid_to_cover,cut_off_yield,avg_yield,source\n")

        for r in records:
            output.write(
                f"{r.date},{r.instrument_type},{r.tenor_label},{r.tenor_days},"
                f"{r.amount_offered or ''},{r.amount_sold or ''},{r.bid_to_cover or ''},"
                f"{r.cut_off_yield or ''},{r.avg_yield or ''},{r.source}\n"
            )

        output.seek(0)

        return StreamingResponse(
            output,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=auctions_{start_date}_to_{end_date}.csv"}
        )
    except Exception as e:
        logger.error(f"Error exporting auctions CSV: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Secondary trading endpoints
@router.get("/api/secondary/latest", response_model=List[SecondaryTradingRecord])
async def get_latest_secondary_trading(
    limit: int = Query(100, description="Number of recent records to return")
):
    """Get latest secondary trading statistics"""
    try:
        sql = """
        SELECT * FROM gov_secondary_trading
        ORDER BY date DESC
        LIMIT ?
        """

        result = db_manager.con.execute(sql, [limit]).fetchall()
        columns = [desc[0] for desc in db_manager.con.description]
        records = [dict(zip(columns, row)) for row in result]

        return [SecondaryTradingRecord(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching latest secondary trading: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/secondary/range", response_model=List[SecondaryTradingRecord])
async def get_secondary_trading_range(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
    segment: Optional[str] = Query(None, description="Filter by segment"),
    bucket: Optional[str] = Query(None, description="Filter by bucket/investor type")
):
    """Get secondary trading statistics for a date range"""
    try:
        conditions = ["date >= ?", "date <= ?"]
        params = [start_date, end_date]

        if segment:
            conditions.append("segment = ?")
            params.append(segment)

        if bucket:
            conditions.append("bucket_label = ?")
            params.append(bucket)

        where_clause = "WHERE " + " AND ".join(conditions)

        sql = f"""
        SELECT * FROM gov_secondary_trading
        {where_clause}
        ORDER BY date DESC
        """

        result = db_manager.con.execute(sql, params).fetchall()
        columns = [desc[0] for desc in db_manager.con.description]
        records = [dict(zip(columns, row)) for row in result]

        return [SecondaryTradingRecord(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching secondary trading range: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/export/secondary.csv")
async def export_secondary_csv(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format")
):
    """Export secondary trading statistics as CSV"""
    try:
        records = await get_secondary_trading_range(start_date, end_date, segment=None, bucket=None)

        # Create CSV
        output = StringIO()
        output.write("date,segment,bucket_label,volume,value,avg_yield,source\n")

        for r in records:
            output.write(
                f"{r.date},{r.segment},{r.bucket_label},"
                f"{r.volume or ''},{r.value or ''},{r.avg_yield or ''},{r.source}\n"
            )

        output.seek(0)

        return StreamingResponse(
            output,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=secondary_{start_date}_to_{end_date}.csv"}
        )
    except Exception as e:
        logger.error(f"Error exporting secondary CSV: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Policy rates endpoints
@router.get("/api/policy-rates/latest", response_model=List[PolicyRateRecord])
async def get_latest_policy_rates():
    """Get latest policy rates"""
    try:
        sql = """
        SELECT * FROM policy_rates
        WHERE date = (SELECT MAX(date) FROM policy_rates)
        ORDER BY rate_name
        """

        result = db_manager.con.execute(sql).fetchall()
        columns = [desc[0] for desc in db_manager.con.description]
        records = [dict(zip(columns, row)) for row in result]

        return [PolicyRateRecord(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching latest policy rates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/policy-rates/range", response_model=List[PolicyRateRecord])
async def get_policy_rates_range(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
    rate_name: Optional[str] = Query(None, description="Filter by rate name")
):
    """Get policy rates for a date range"""
    try:
        conditions = ["date >= ?", "date <= ?"]
        params = [start_date, end_date]

        if rate_name:
            conditions.append("rate_name = ?")
            params.append(rate_name)

        where_clause = "WHERE " + " AND ".join(conditions)

        sql = f"""
        SELECT * FROM policy_rates
        {where_clause}
        ORDER BY date DESC, rate_name
        """

        result = db_manager.con.execute(sql, params).fetchall()
        columns = [desc[0] for desc in db_manager.con.description]
        records = [dict(zip(columns, row)) for row in result]

        return [PolicyRateRecord(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching policy rates range: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/export/policy-rates.csv")
async def export_policy_rates_csv(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format")
):
    """Export policy rates as CSV"""
    try:
        records = await get_policy_rates_range(start_date, end_date, rate_name=None)

        # Create CSV
        output = StringIO()
        output.write("date,rate_name,rate,source\n")

        for r in records:
            output.write(f"{r.date},{r.rate_name},{r.rate},{r.source}\n")

        output.seek(0)

        return StreamingResponse(
            output,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=policy_rates_{start_date}_to_{end_date}.csv"}
        )
    except Exception as e:
        logger.error(f"Error exporting policy rates CSV: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Bank deposit/loan rates (Lai_suat bridge)
class BankRateRecord(BaseModel):
    date: date
    product_group: str
    series_code: str
    bank_name: str
    term_months: int
    term_label: Optional[str] = None
    rate_min_pct: Optional[float] = None
    rate_max_pct: Optional[float] = None
    rate_pct: Optional[float] = None
    source_url: Optional[str] = None
    source_priority: Optional[int] = None
    scraped_at: Optional[datetime] = None
    fetched_at: datetime
    source: str


class LaiSuatSeries(BaseModel):
    code: str
    product_group: str
    description: Optional[str] = None


class LaiSuatLatestResponse(BaseModel):
    rows: list[dict]
    meta: dict


@router.get("/api/bank-rates/latest", response_model=List[BankRateRecord])
async def get_latest_bank_rates(
    product_group: Optional[str] = Query(None, description="deposit or loan"),
    series_code: Optional[str] = Query(None, description="e.g., deposit_online, loan_tin_chap"),
    bank_name: Optional[str] = Query(None, description="Bank short name as stored (e.g., VCB)"),
    term_months: Optional[int] = Query(None, description="Term in months; use -1 for no-term series"),
):
    """Get latest bank deposit/loan rates (max(date) for the given filter)."""
    try:
        conditions = []
        params = []

        max_pr = int(getattr(settings, "lai_suat_max_source_priority", 1))
        conditions.append(
            "((source_priority IS NULL OR source_priority <= ?) OR (source_url IS NOT NULL AND source_url LIKE ?) OR series_code = 'deposit_online')"
        )
        params.append(int(max_pr))
        params.append("%timo.vn/%")

        if product_group:
            conditions.append("product_group = ?")
            params.append(product_group)
        if series_code:
            conditions.append("series_code = ?")
            params.append(series_code)
        if bank_name:
            conditions.append("bank_name = ?")
            params.append(bank_name)
        if term_months is not None:
            conditions.append("term_months = ?")
            params.append(int(term_months))

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        max_date = db_manager.con.execute(f"SELECT MAX(date) FROM bank_rates {where}", params).fetchone()[0]
        if max_date is None:
            return []

        records = db_manager.get_bank_rates(
            product_group=product_group,
            series_code=series_code,
            bank_name=bank_name,
            term_months=term_months,
            start_date=str(max_date),
            end_date=str(max_date),
        )
        return [BankRateRecord(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching latest bank rates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/bank-rates/history", response_model=List[BankRateRecord])
async def get_bank_rates_history(
    bank_name: str = Query(..., description="Bank short name as stored (e.g., VCB)"),
    series_code: str = Query(..., description="Series code (e.g., deposit_online, loan_tin_chap)"),
    term_months: int = Query(-1, description="Term in months; use -1 for no-term series"),
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
):
    """Get bank rate history for a specific (bank, series, term) range."""
    try:
        records = db_manager.get_bank_rates(
            bank_name=bank_name,
            series_code=series_code,
            term_months=term_months,
            start_date=start_date,
            end_date=end_date,
            limit=None,
        )
        # API returns newest-first by default; reverse for chart friendliness.
        records = list(reversed(records))
        return [BankRateRecord(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching bank rates history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class LaiSuatHistoryPoint(BaseModel):
    date: date
    rate_pct: Optional[float] = None
    rate_min_pct: Optional[float] = None
    rate_max_pct: Optional[float] = None


class LaiSuatHistoryResponse(BaseModel):
    bank_name: str
    series_code: str
    term_months: Optional[int] = None
    points: List[LaiSuatHistoryPoint]


_LAI_SUAT_SERIES_LABELS = {
    "deposit_online": "Gửi online",
    "deposit_tai_quay": "Gửi tại quầy",
    "loan_the_chap": "Vay thế chấp",
    "loan_tin_chap": "Vay tín chấp",
}


def _lai_suat_series_label(code: str, product_group: Optional[str] = None) -> str:
    label = _LAI_SUAT_SERIES_LABELS.get(code)
    if label:
        return label
    if product_group == "deposit":
        return f"Tiền gửi ({code})"
    if product_group == "loan":
        return f"Cho vay ({code})"
    return code


def _lai_suat_paths() -> dict[str, Path]:
    root = Path(settings.lai_suat_root)
    sqlite_path = Path(settings.lai_suat_db_path)
    return {
        "root": root,
        "sqlite": sqlite_path,
        "logs_dir": root / "logs",
    }


def _tail_file(path: Path, max_lines: int = 250) -> str:
    if not path.exists() or not path.is_file():
        return ""
    from collections import deque
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            return "".join(deque(f, maxlen=int(max_lines)))
    except Exception:
        return ""


def _latest_log_file(logs_dir: Path) -> Optional[Path]:
    if not logs_dir.exists():
        return None
    candidates = sorted(logs_dir.glob("scrape_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _run_lai_suat_scrape() -> dict:
    paths = _lai_suat_paths()
    root = paths["root"]
    sqlite_path = paths["sqlite"]
    logs_dir = paths["logs_dir"]

    if not root.exists():
        raise FileNotFoundError(f"Lai_suat root not found: {root}")

    cmd = [
        sys.executable,
        "-m",
        "app.cli",
        "--db",
        str(sqlite_path),
        "scrape",
        "--all",
        "--no-anomaly-exit",
    ]

    result = subprocess.run(
        cmd,
        cwd=str(root),
        env={
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": str(root),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / datetime.now().strftime("scrape_%Y%m%d.log")
    try:
        with log_file.open("a", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write(f"Started: {datetime.now().isoformat()}\n")
            f.write(f"Command: {' '.join(cmd)}\n")
            f.write(f"DB: {sqlite_path}\n")
            f.write(f"Exit: {result.returncode}\n")
            if result.stdout:
                f.write("\n[stdout]\n")
                f.write(result.stdout)
                if not result.stdout.endswith("\n"):
                    f.write("\n")
            if result.stderr:
                f.write("\n[stderr]\n")
                f.write(result.stderr)
                if not result.stderr.endswith("\n"):
                    f.write("\n")
            f.write("=" * 80 + "\n\n")
    except Exception:
        pass

    return {
        "exit_code": result.returncode,
        "stdout_tail": (result.stdout or "")[-2000:],
        "stderr_tail": (result.stderr or "")[-2000:],
        "log_path": str(log_file) if log_file else None,
    }


@router.get("/api/admin/lai-suat/status")
async def admin_lai_suat_status():
    """Admin: status for Lai_suat SQLite + DuckDB mirror."""
    paths = _lai_suat_paths()
    sqlite_path = paths["sqlite"]
    logs_dir = paths["logs_dir"]

    sqlite_info: dict = {"available": False}
    try:
        if sqlite_path.exists():
            con = sqlite3.connect(str(sqlite_path))
            try:
                min_day, max_day, cnt = con.execute(
                    "SELECT MIN(observed_day), MAX(observed_day), COUNT(*) FROM observations WHERE observed_day IS NOT NULL"
                ).fetchone()
                last_scraped = con.execute("SELECT MAX(scraped_at) FROM sources").fetchone()[0]
                sqlite_info = {
                    "available": True,
                    "path": str(sqlite_path),
                    "min_date": min_day,
                    "max_date": max_day,
                    "observations_count": cnt,
                    "last_scraped_at": last_scraped,
                }
            finally:
                con.close()
        else:
            sqlite_info = {"available": False, "error": f"SQLite not found: {sqlite_path}"}
    except Exception as e:
        sqlite_info = {"available": False, "error": str(e)}

    duck_info: dict = {"available": False, "path": str(db_manager.db_path) if getattr(db_manager, "db_path", None) else None}
    try:
        max_date = db_manager.con.execute("SELECT MAX(date) FROM bank_rates").fetchone()[0]
        if max_date is not None:
            row_count = db_manager.con.execute("SELECT COUNT(*) FROM bank_rates").fetchone()[0]
            min_date = db_manager.con.execute("SELECT MIN(date) FROM bank_rates").fetchone()[0]
            duck_info = {
                "available": True,
                "path": str(db_manager.db_path) if getattr(db_manager, "db_path", None) else None,
                "row_count": row_count,
                "min_date": str(min_date) if min_date is not None else None,
                "max_date": str(max_date),
            }
        else:
            duck_info = {
                "available": False,
                "path": str(db_manager.db_path) if getattr(db_manager, "db_path", None) else None,
                "row_count": 0,
                "min_date": None,
                "max_date": None,
            }
    except Exception as e:
        duck_info = {"available": False, "error": str(e)}

    log_file = _latest_log_file(logs_dir)
    return {
        "sqlite": sqlite_info,
        "duckdb": duck_info,
        "log": {
            "path": str(log_file) if log_file else None,
        },
    }


@router.get("/api/admin/lai-suat/log-tail")
async def admin_lai_suat_log_tail(
    lines: int = Query(250, description="Max lines from latest scrape log"),
):
    """Admin: tail latest Lai_suat scrape log."""
    paths = _lai_suat_paths()
    log_file = _latest_log_file(paths["logs_dir"])
    if not log_file:
        return {"path": None, "tail": ""}
    return {"path": str(log_file), "tail": _tail_file(log_file, max_lines=lines)}


@router.post("/api/admin/lai-suat/scrape")
async def admin_lai_suat_scrape():
    """Admin: run Lai_suat crawler (updates SQLite)."""
    try:
        result = _run_lai_suat_scrape()
        return result
    except Exception as e:
        logger.error(f"Error running Lai_suat scrape: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/lai-suat/update-today")
async def admin_lai_suat_update_today():
    """Admin: run scraper then sync latest observed day into DuckDB bank_rates."""
    try:
        scrape = _run_lai_suat_scrape()
        paths = _lai_suat_paths()
        sqlite_path = paths["sqlite"]

        latest_day = None
        con = sqlite3.connect(str(sqlite_path))
        try:
            latest_day = con.execute(
                "SELECT MAX(observed_day) FROM observations WHERE observed_day IS NOT NULL"
            ).fetchone()[0]
        finally:
            con.close()

        if not latest_day:
            return {
                "scrape_exit_code": scrape.get("exit_code"),
                "rows_inserted": 0,
                "date": None,
                "note": "No observed_day found in SQLite",
            }

        latest_date = datetime.fromisoformat(str(latest_day)).date()

        from app.providers.lai_suat_rates import LaiSuatRatesProvider

        with LaiSuatRatesProvider() as provider:
            records = provider.read_range(latest_date, latest_date, run_scraper=False)
        rows_inserted = db_manager.insert_bank_rates(records) if records else 0

        return {
            "scrape_exit_code": scrape.get("exit_code"),
            "rows_inserted": rows_inserted,
            "date": latest_date.isoformat(),
        }
    except Exception as e:
        logger.error(f"Error updating Lai_suat today: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/lai-suat/sync-range")
async def admin_lai_suat_sync_range(
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD (default: SQLite min)"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD (default: SQLite max)"),
):
    """Admin: sync a date range from Lai_suat SQLite into DuckDB bank_rates (no scraper run)."""
    try:
        sqlite_path = Path(settings.lai_suat_db_path)
        if not sqlite_path.exists():
            raise HTTPException(status_code=500, detail=f"SQLite not found: {sqlite_path}")

        con = sqlite3.connect(str(sqlite_path))
        try:
            min_day, max_day = con.execute(
                "SELECT MIN(observed_day), MAX(observed_day) FROM observations WHERE observed_day IS NOT NULL"
            ).fetchone()
        finally:
            con.close()

        if not min_day or not max_day:
            return {"rows_inserted": 0, "start_date": None, "end_date": None, "note": "No observed_day data"}

        if start_date is None:
            start_date = str(min_day)
        if end_date is None:
            end_date = str(max_day)

        from datetime import datetime as _dt
        start = _dt.fromisoformat(start_date).date()
        end = _dt.fromisoformat(end_date).date()

        from app.providers.lai_suat_rates import LaiSuatRatesProvider

        with LaiSuatRatesProvider() as provider:
            records = provider.read_range(start, end, run_scraper=False)
        rows_inserted = db_manager.insert_bank_rates(records) if records else 0

        return {"rows_inserted": rows_inserted, "start_date": start.isoformat(), "end_date": end.isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing Lai_suat range: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/lai-suat/sync-all")
async def admin_lai_suat_sync_all():
    """Admin: sync full available history from Lai_suat SQLite into DuckDB bank_rates."""
    return await admin_lai_suat_sync_range(start_date=None, end_date=None)


@router.post("/api/admin/lai-suat/sync-missing")
async def admin_lai_suat_sync_missing():
    """
    Admin: sync only the missing date range from SQLite -> DuckDB.

    - If DuckDB has no bank_rates yet: sync-all
    - Else: sync from (duckdb_max_date + 1) to sqlite_max_date
    """
    try:
        sqlite_path = Path(settings.lai_suat_db_path)
        if not sqlite_path.exists():
            raise HTTPException(status_code=500, detail=f"SQLite not found: {sqlite_path}")

        con = sqlite3.connect(str(sqlite_path))
        try:
            sqlite_min, sqlite_max = con.execute(
                "SELECT MIN(observed_day), MAX(observed_day) FROM observations WHERE observed_day IS NOT NULL"
            ).fetchone()
        finally:
            con.close()

        if not sqlite_min or not sqlite_max:
            return {"rows_inserted": 0, "start_date": None, "end_date": None, "note": "No observed_day data"}

        duck_max = None
        try:
            duck_max = db_manager.con.execute("SELECT MAX(date) FROM bank_rates").fetchone()[0]
        except Exception:
            duck_max = None

        from datetime import datetime as _dt, timedelta as _td
        sqlite_max_date = _dt.fromisoformat(str(sqlite_max)).date()
        sqlite_min_date = _dt.fromisoformat(str(sqlite_min)).date()

        if duck_max is None:
            return await admin_lai_suat_sync_range(
                start_date=sqlite_min_date.isoformat(),
                end_date=sqlite_max_date.isoformat(),
            )

        start = duck_max + _td(days=1)
        end = sqlite_max_date
        if start > end:
            # Refresh latest day anyway (scraped_at/rates may have changed)
            return await admin_lai_suat_sync_range(
                start_date=sqlite_max_date.isoformat(),
                end_date=sqlite_max_date.isoformat(),
            )

        return await admin_lai_suat_sync_range(start_date=start.isoformat(), end_date=end.isoformat())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing missing Lai_suat range: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _lai_suat_ui_paths() -> dict[str, Path]:
    project_root = Path(settings.lai_suat_root).parent
    frontend_dir = Path(settings.lai_suat_root) / "frontend"
    # Keep PID/log paths consistent with the running server DB location.
    # This avoids split-brain behavior when the repo is on iCloud Drive and
    # LaunchAgents/scripts use `~/Library/Application Support/vn-bond-lab`.
    state_dir = Path(settings.db_path).expanduser().resolve().parent
    logs_dir = state_dir / "logs"
    pids_dir = state_dir / "pids"
    logs_dir.mkdir(parents=True, exist_ok=True)
    pids_dir.mkdir(parents=True, exist_ok=True)
    return {
        "project_root": project_root,
        "frontend_dir": frontend_dir,
        "pid_file": pids_dir / "lai_suat_ui_3001.pid",
        "log_file": logs_dir / "lai_suat_ui_3001.log",
    }


def _pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


@router.get("/api/admin/lai-suat/ui/status")
async def admin_lai_suat_ui_status():
    """Admin: status for embedded Lai_suat Next.js UI process."""
    paths = _lai_suat_ui_paths()
    pid_file = paths["pid_file"]
    running = False
    pid: Optional[int] = None

    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            running = _pid_running(pid)
        except Exception:
            running = False

    return {
        "running": running,
        "pid": pid if running else None,
        "port": 3001,
        "url": "http://127.0.0.1:3001/?embed=1",
        "log": str(paths["log_file"]),
    }


@router.get("/api/admin/lai-suat/ui/log-tail")
async def admin_lai_suat_ui_log_tail(
    lines: int = Query(200, description="Max lines from UI log"),
):
    paths = _lai_suat_ui_paths()
    return {"path": str(paths["log_file"]), "tail": _tail_file(paths["log_file"], max_lines=lines)}


@router.post("/api/admin/lai-suat/ui/start")
async def admin_lai_suat_ui_start():
    """Admin: start Lai_suat Next.js UI (dev server)."""
    paths = _lai_suat_ui_paths()
    frontend_dir = paths["frontend_dir"]
    pid_file = paths["pid_file"]
    log_file = paths["log_file"]

    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            if _pid_running(pid):
                return {"status": "already_running", "pid": pid, "url": "http://127.0.0.1:3001/?embed=1"}
        except Exception:
            pass

    if not frontend_dir.exists():
        raise HTTPException(status_code=500, detail=f"frontend dir not found: {frontend_dir}")

    log_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.parent.mkdir(parents=True, exist_ok=True)

    # Point the embedded UI to Bond Lab's compatibility endpoints.
    api_base = "http://127.0.0.1:8001/api/lai-suat"

    try:
        with log_file.open("a", encoding="utf-8") as lf:
            lf.write(f"\n=== START {datetime.now().isoformat()} ===\n")
            lf.flush()

            proc = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=str(frontend_dir),
                env={
                    **os.environ,
                    "NEXT_PUBLIC_API_BASE": api_base,
                    "PYTHONUNBUFFERED": "1",
                },
                stdout=lf,
                stderr=subprocess.STDOUT,
                text=True,
            )

        pid_file.write_text(str(proc.pid))
        return {"status": "started", "pid": proc.pid, "url": "http://127.0.0.1:3001/?embed=1"}
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="npm not found. Please install Node.js / npm.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/lai-suat/ui/stop")
async def admin_lai_suat_ui_stop():
    """Admin: stop Lai_suat Next.js UI."""
    paths = _lai_suat_ui_paths()
    pid_file = paths["pid_file"]
    if not pid_file.exists():
        return {"status": "not_running"}

    try:
        pid = int(pid_file.read_text().strip())
    except Exception:
        pid_file.unlink(missing_ok=True)
        return {"status": "not_running"}

    if not _pid_running(pid):
        pid_file.unlink(missing_ok=True)
        return {"status": "not_running"}

    try:
        os.kill(pid, 15)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    pid_file.unlink(missing_ok=True)
    return {"status": "stopped"}


@router.get("/api/lai-suat/health")
async def lai_suat_health():
    try:
        if db_manager is None:
            return {"ok": False}
        # Health: DuckDB must be reachable and have bank_rates.
        db_manager.con.execute("SELECT 1 FROM bank_rates LIMIT 1").fetchone()
        return {"ok": True}
    except Exception as e:
        return {"ok": False}


@router.get("/api/lai-suat/meta/latest")
async def lai_suat_meta_latest():
    try:
        if db_manager is None:
            raise HTTPException(status_code=500, detail="Database not initialized")

        rows = db_manager.con.execute(
            """
            SELECT
              source_url,
              strftime(MAX(scraped_at), '%Y-%m-%dT%H:%M:%S') || 'Z' AS latest_scraped_at
            FROM bank_rates
            WHERE source_url IS NOT NULL AND scraped_at IS NOT NULL
            GROUP BY source_url
            """
        ).fetchall()

        scraped_at_by_url: dict[str, str] = {}
        for source_url, latest_scraped_at in rows:
            if source_url and latest_scraped_at:
                scraped_at_by_url[str(source_url)] = str(latest_scraped_at)

        latest_scraped_at = db_manager.con.execute(
            "SELECT strftime(MAX(scraped_at), '%Y-%m-%dT%H:%M:%S') || 'Z' FROM bank_rates WHERE scraped_at IS NOT NULL"
        ).fetchone()[0]
        sources_count = db_manager.con.execute(
            "SELECT COUNT(DISTINCT source_url) FROM bank_rates WHERE source_url IS NOT NULL"
        ).fetchone()[0]
        observations_count = db_manager.con.execute("SELECT COUNT(*) FROM bank_rates").fetchone()[0]

        return {
            "scraped_at_by_url": scraped_at_by_url,
            "latest_scraped_at": str(latest_scraped_at) if latest_scraped_at is not None else None,
            "sources_count": int(sources_count or 0),
            "observations_count": int(observations_count or 0),
            "last_anomaly": None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/lai-suat/banks", response_model=List[str])
async def lai_suat_banks():
    try:
        if db_manager is None:
            raise HTTPException(status_code=500, detail="Database not initialized")
        rows = db_manager.con.execute(
            "SELECT DISTINCT bank_name FROM bank_rates ORDER BY bank_name"
        ).fetchall()
        return [str(r[0]) for r in rows if r and r[0] is not None]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/lai-suat/series", response_model=List[LaiSuatSeries])
async def lai_suat_series():
    try:
        if db_manager is None:
            raise HTTPException(status_code=500, detail="Database not initialized")
        rows = db_manager.con.execute(
            """
            SELECT DISTINCT product_group, series_code
            FROM bank_rates
            ORDER BY product_group, series_code
            """
        ).fetchall()
        out: list[LaiSuatSeries] = []
        for product_group, code in rows:
            out.append(
                LaiSuatSeries(
                    code=str(code),
                    product_group=str(product_group),
                    description=_lai_suat_series_label(str(code), str(product_group)),
                )
            )
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/lai-suat/latest", response_model=LaiSuatLatestResponse)
async def lai_suat_latest(
    series_code: str = Query(..., description="Series code (e.g., deposit_online, loan_the_chap)"),
    term_months: Optional[int] = Query(None, description="Term in months (required for deposit series)"),
    sort: str = Query("rate_desc", description="Sort order: rate_desc, rate_asc, bank_asc"),
):
    try:
        if series_code.startswith("deposit_") and term_months is None:
            raise HTTPException(status_code=400, detail="term_months is required for deposit series")
        if series_code.startswith("loan_") and term_months is not None:
            raise HTTPException(status_code=400, detail="term_months should not be provided for loan series")
        if db_manager is None:
            raise HTTPException(status_code=500, detail="Database not initialized")

        params: list = [series_code]
        where = "WHERE series_code = ?"
        if term_months is not None:
            where += " AND term_months = ?"
            params.append(int(term_months))
        else:
            # Loans have term_months=-1 in DuckDB.
            where += " AND term_months = -1"

        max_date = db_manager.con.execute(
            f"SELECT MAX(date) FROM bank_rates {where}",
            params,
        ).fetchone()[0]
        if max_date is None:
            return {"rows": [], "meta": {"series_code": series_code, "term_months": term_months, "sort": sort, "count": 0}}

        params2 = [str(max_date), *params]
        where2 = f"WHERE date = ? AND {where[len('WHERE '):]}"

        order_by = "ORDER BY bank_name"
        if sort == "rate_desc":
            order_by = "ORDER BY COALESCE(rate_pct, rate_max_pct, rate_min_pct) DESC, bank_name"
        elif sort == "rate_asc":
            order_by = "ORDER BY COALESCE(rate_pct, rate_max_pct, rate_min_pct) ASC, bank_name"
        elif sort == "bank_asc":
            order_by = "ORDER BY bank_name"

        rows = db_manager.con.execute(
            f"""
            SELECT
              bank_name,
              series_code,
              term_months,
              term_label,
              rate_pct,
              rate_min_pct,
              rate_max_pct,
              CAST(NULL AS VARCHAR) AS raw_value,
              CAST(date AS VARCHAR) AS observed_day,
              CASE
                WHEN scraped_at IS NULL THEN NULL
                ELSE strftime(scraped_at, '%Y-%m-%dT%H:%M:%S') || 'Z'
              END AS scraped_at,
              source_url
            FROM bank_rates
            {where2}
            {order_by}
            """,
            params2,
        ).fetchall()

        cols = [d[0] for d in db_manager.con.description]
        records = [dict(zip(cols, r)) for r in rows]
        return {
            "rows": records,
            "meta": {"series_code": series_code, "term_months": term_months, "sort": sort, "count": len(records)},
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class BankRateAveragesLatest(BaseModel):
    deposit_term_months: int = 12
    as_of_date: Optional[str] = None
    deposit_latest_date: Optional[str] = None
    loan_latest_date: Optional[str] = None
    deposit_avg_12m: Optional[float] = None
    loan_avg: Optional[float] = None
    note: Optional[str] = None


class BankRateAveragesPoint(BaseModel):
    date: date
    deposit_avg_12m: Optional[float] = None
    loan_avg: Optional[float] = None


@router.get("/api/bank-rates/averages/latest", response_model=BankRateAveragesLatest)
async def get_bank_rate_averages_latest(
    deposit_term_months: int = Query(12, ge=1, le=120, description="Deposit term in months used for average"),
    align_common_date: bool = Query(
        True, description="If true, compute both averages on the latest common available date"
    ),
):
    """
    Latest bank-rate averages from DuckDB `bank_rates`.

    Notes:
    - Deposit: per-bank best (max) rate for the given term, then average across banks.
    - Loan: per-bank best (min) rate across loan series, then average across banks.
    - When deposit and loan latest dates differ, `align_common_date=true` computes both on the latest common date.
    """
    try:
        max_pr = int(getattr(settings, "lai_suat_max_source_priority", 1))
        dep_latest = db_manager.con.execute(
            """
            SELECT MAX(date)
            FROM bank_rates
            WHERE product_group = 'deposit'
              AND term_months = ?
              AND rate_pct IS NOT NULL
              AND ((source_priority IS NULL OR source_priority <= ?) OR (source_url IS NOT NULL AND source_url LIKE ?))
            """,
            [int(deposit_term_months), int(max_pr), "%timo.vn/%"],
        ).fetchone()[0]
        loan_latest = db_manager.con.execute(
            """
            SELECT MAX(date)
            FROM bank_rates
            WHERE product_group = 'loan'
              AND (rate_min_pct IS NOT NULL OR rate_pct IS NOT NULL OR rate_max_pct IS NOT NULL)
              AND ((source_priority IS NULL OR source_priority <= ?) OR (source_url IS NOT NULL AND source_url LIKE ?))
            """,
            [int(max_pr), "%timo.vn/%"],
        ).fetchone()[0]

        if dep_latest is None and loan_latest is None:
            return BankRateAveragesLatest(deposit_term_months=int(deposit_term_months))

        as_of = None
        if align_common_date and dep_latest is not None and loan_latest is not None:
            as_of = min(dep_latest, loan_latest)
        else:
            as_of = dep_latest or loan_latest

        deposit_avg = None
        if as_of is not None:
            deposit_avg = db_manager.con.execute(
                """
                WITH per_bank AS (
                  SELECT
                    bank_name,
                    MAX(rate_pct) AS best_rate
                  FROM bank_rates
                  WHERE product_group = 'deposit'
                    AND term_months = ?
                    AND date = ?
                    AND rate_pct IS NOT NULL
                    AND ((source_priority IS NULL OR source_priority <= ?) OR (source_url IS NOT NULL AND source_url LIKE ?))
                  GROUP BY bank_name
                )
                SELECT AVG(best_rate) FROM per_bank
                """,
                [int(deposit_term_months), str(as_of), int(max_pr), "%timo.vn/%"],
            ).fetchone()[0]

        loan_avg = None
        if as_of is not None:
            loan_avg = db_manager.con.execute(
                """
                WITH per_bank AS (
                  SELECT
                    bank_name,
                    MIN(
                      CASE
                        WHEN rate_min_pct IS NOT NULL THEN rate_min_pct
                        WHEN rate_pct IS NOT NULL THEN rate_pct
                        WHEN rate_max_pct IS NOT NULL THEN rate_max_pct
                        ELSE NULL
                      END
                    ) AS best_rate
                  FROM bank_rates
                  WHERE product_group = 'loan'
                    AND date = ?
                    AND (rate_min_pct IS NOT NULL OR rate_pct IS NOT NULL OR rate_max_pct IS NOT NULL)
                    AND ((source_priority IS NULL OR source_priority <= ?) OR (source_url IS NOT NULL AND source_url LIKE ?))
                  GROUP BY bank_name
                )
                SELECT AVG(best_rate) FROM per_bank
                """,
                [str(as_of), int(max_pr), "%timo.vn/%"],
            ).fetchone()[0]

        note = None
        if dep_latest is not None and loan_latest is not None and str(dep_latest) != str(loan_latest):
            if align_common_date:
                note = (
                    "Ngày cập nhật tiền gửi và cho vay lệch nhau; phần trung bình dùng ngày chung gần nhất để so sánh."
                )
            else:
                note = "Ngày cập nhật tiền gửi và cho vay lệch nhau; mỗi chỉ số dùng ngày mới nhất của chính nó."

        return BankRateAveragesLatest(
            deposit_term_months=int(deposit_term_months),
            as_of_date=str(as_of) if as_of is not None else None,
            deposit_latest_date=str(dep_latest) if dep_latest is not None else None,
            loan_latest_date=str(loan_latest) if loan_latest is not None else None,
            deposit_avg_12m=float(deposit_avg) if deposit_avg is not None else None,
            loan_avg=float(loan_avg) if loan_avg is not None else None,
            note=note,
        )
    except Exception as e:
        logger.error(f"Error fetching bank rate averages latest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/bank-rates/averages/timeseries", response_model=List[BankRateAveragesPoint])
async def get_bank_rate_averages_timeseries(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
    deposit_term_months: int = Query(12, ge=1, le=120, description="Deposit term in months used for average"),
):
    """
    Time series of bank-rate averages from DuckDB `bank_rates`.

    Deposit: per-bank best (max) rate for the chosen term → average across banks.
    Loan: per-bank best (min) rate across loan series → average across banks.
    """
    try:
        max_pr = int(getattr(settings, "lai_suat_max_source_priority", 1))
        rows = db_manager.con.execute(
            """
            WITH dep AS (
              SELECT
                date,
                AVG(best_rate) AS deposit_avg_12m
              FROM (
                SELECT date, bank_name, MAX(rate_pct) AS best_rate
                FROM bank_rates
                WHERE product_group = 'deposit'
                  AND term_months = ?
                  AND rate_pct IS NOT NULL
                  AND ((source_priority IS NULL OR source_priority <= ?) OR (source_url IS NOT NULL AND source_url LIKE ?))
                  AND date >= ? AND date <= ?
                GROUP BY date, bank_name
              )
              GROUP BY date
            ),
            loan AS (
              SELECT
                date,
                AVG(best_rate) AS loan_avg
              FROM (
                SELECT
                  date,
                  bank_name,
                  MIN(
                    CASE
                      WHEN rate_min_pct IS NOT NULL THEN rate_min_pct
                      WHEN rate_pct IS NOT NULL THEN rate_pct
                      WHEN rate_max_pct IS NOT NULL THEN rate_max_pct
                      ELSE NULL
                    END
                  ) AS best_rate
                FROM bank_rates
                WHERE product_group = 'loan'
                  AND (rate_min_pct IS NOT NULL OR rate_pct IS NOT NULL OR rate_max_pct IS NOT NULL)
                  AND ((source_priority IS NULL OR source_priority <= ?) OR (source_url IS NOT NULL AND source_url LIKE ?))
                  AND date >= ? AND date <= ?
                GROUP BY date, bank_name
              )
              GROUP BY date
            )
            SELECT
              COALESCE(dep.date, loan.date) AS date,
              dep.deposit_avg_12m AS deposit_avg_12m,
              loan.loan_avg AS loan_avg
            FROM dep
            FULL OUTER JOIN loan ON dep.date = loan.date
            WHERE COALESCE(dep.date, loan.date) >= ? AND COALESCE(dep.date, loan.date) <= ?
            ORDER BY date
            """,
            [
                int(deposit_term_months),
                int(max_pr),
                "%timo.vn/%",
                start_date,
                end_date,
                int(max_pr),
                "%timo.vn/%",
                start_date,
                end_date,
                start_date,
                end_date,
            ],
        ).fetchall()

        out: list[BankRateAveragesPoint] = []
        for r in rows:
            if not r or r[0] is None:
                continue
            out.append(
                BankRateAveragesPoint(
                    date=r[0],
                    deposit_avg_12m=float(r[1]) if r[1] is not None else None,
                    loan_avg=float(r[2]) if r[2] is not None else None,
                )
            )
        return out
    except Exception as e:
        logger.error(f"Error fetching bank rate averages timeseries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/lai-suat/averages/latest", response_model=BankRateAveragesLatest)
async def lai_suat_averages_latest(
    deposit_term_months: int = Query(12, ge=1, le=120, description="Deposit term in months used for average"),
    align_common_date: bool = Query(
        True, description="If true, compute both averages on the latest common available date"
    ),
):
    """
    Alias endpoint for the Lai_suat UI: averages computed from DuckDB `bank_rates`.
    """
    return await get_bank_rate_averages_latest(
        deposit_term_months=deposit_term_months,
        align_common_date=align_common_date,
    )


@router.get("/api/lai-suat/averages/timeseries", response_model=List[BankRateAveragesPoint])
async def lai_suat_averages_timeseries(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
    deposit_term_months: int = Query(12, ge=1, le=120, description="Deposit term in months used for average"),
):
    """
    Alias endpoint for the Lai_suat UI: averages timeseries from DuckDB `bank_rates`.
    """
    return await get_bank_rate_averages_timeseries(
        start_date=start_date,
        end_date=end_date,
        deposit_term_months=deposit_term_months,
    )


@router.get("/api/lai-suat/history")
async def lai_suat_history(
    bank_name: str = Query(..., description="Bank name"),
    series_code: str = Query(..., description="Series code"),
    term_months: Optional[int] = Query(None, description="Term in months (required for deposit series)"),
    limit: int = Query(120, description="Max history points"),
):
    try:
        if series_code.startswith("deposit_") and term_months is None:
            raise HTTPException(status_code=400, detail="term_months is required for deposit series")
        if series_code.startswith("loan_") and term_months is not None:
            raise HTTPException(status_code=400, detail="term_months should not be provided for loan series")
        if db_manager is None:
            raise HTTPException(status_code=500, detail="Database not initialized")

        term = int(term_months) if term_months is not None else -1
        rows = db_manager.con.execute(
            """
            SELECT
              CASE
                WHEN scraped_at IS NULL THEN NULL
                ELSE strftime(scraped_at, '%Y-%m-%dT%H:%M:%S') || 'Z'
              END AS scraped_at,
              rate_pct,
              rate_min_pct,
              rate_max_pct
            FROM bank_rates
            WHERE bank_name = ?
              AND series_code = ?
              AND term_months = ?
            ORDER BY date DESC
            LIMIT ?
            """,
            [bank_name, series_code, term, int(limit)],
        ).fetchall()
        cols = [d[0] for d in db_manager.con.description]
        points = [dict(zip(cols, r)) for r in reversed(rows)]

        return {
            "points": points,
            "meta": {
                "bank_name": bank_name,
                "series_code": series_code,
                "term_months": term_months,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Transmission analytics endpoints
class TransmissionMetricRecord(BaseModel):
    date: date
    metric_name: str
    metric_value: Optional[float]
    metric_value_text: Optional[str] = None
    source_components: str
    computed_at: datetime

class TransmissionAlertRecord(BaseModel):
    id: int
    date: date
    alert_type: str
    severity: str
    message: str
    metric_value: Optional[float]
    threshold: Optional[float]
    source_data: str
    created_at: datetime


class TransmissionScoreSummary(BaseModel):
    start_date: str
    end_date: str
    n: int
    min: Optional[float] = None
    max: Optional[float] = None
    p20: Optional[float] = None
    p40: Optional[float] = None
    p50: Optional[float] = None
    p60: Optional[float] = None
    p80: Optional[float] = None


class TransmissionComputeRangeResult(BaseModel):
    start_date: str
    end_date: str
    max_dates: int
    skip_existing: bool
    total_dates: int
    pending_dates: int
    processed: int
    succeeded: int
    failed: int
    metrics_rows: int
    alerts_rows: int
    failures: list[dict]


class TransmissionCoverageSummary(BaseModel):
    start_date: str
    end_date: str
    dates_total: int
    score_computable: int
    by_component: dict[str, int]


class TransmissionProgressSummary(BaseModel):
    start_date: str
    end_date: str
    source_dates_total: int
    score_attempted_dates: int
    score_computed_dates: int


class CausalitySeriesInfo(BaseModel):
    id: str
    label: str
    unit: str
    min_obs_recommended: int


class CausalitySeriesCoverage(BaseModel):
    series_id: str
    n_obs: int
    start: Optional[str] = None
    end: Optional[str] = None


class LeadLagResult(BaseModel):
    x: str
    y: str
    diff: bool
    max_lag: int
    n_obs: int
    n_overlap: Optional[int] = None
    m_tests: Optional[int] = None
    lags: List[int]
    correlations: List[Optional[float]]
    n_pairs_by_lag: Optional[List[int]] = None
    p_values: Optional[List[Optional[float]]] = None
    p_values_adj: Optional[List[Optional[float]]] = None
    ci95_low: Optional[List[Optional[float]]] = None
    ci95_high: Optional[List[Optional[float]]] = None
    best_lag: Optional[int] = None
    best_corr: Optional[float] = None
    best_n_pairs: Optional[int] = None
    best_p_value: Optional[float] = None
    best_p_value_adj: Optional[float] = None
    best_ci95_low: Optional[float] = None
    best_ci95_high: Optional[float] = None
    stability: Optional[dict] = None
    warnings: Optional[List[str]] = None


class GrangerResult(BaseModel):
    enabled: bool
    reason: Optional[str] = None
    cause: str
    effect: str
    diff: Optional[bool] = None
    max_lag: Optional[int] = None
    n_obs: Optional[int] = None
    best: Optional[dict] = None
    results: Optional[list[dict]] = None


class VarIrfResult(BaseModel):
    enabled: bool
    reason: Optional[str] = None
    variables: List[str]
    diff: Optional[bool] = None
    max_lag: Optional[int] = None
    selected_lag: Optional[int] = None
    steps: Optional[int] = None
    n_obs: Optional[int] = None
    irf: Optional[dict] = None


class GrangerNetworkResult(BaseModel):
    enabled: bool
    reason: Optional[str] = None
    alpha: Optional[float] = None
    max_lag: Optional[int] = None
    diff: Optional[bool] = None
    nodes: Optional[list[dict]] = None
    edges: Optional[list[dict]] = None


@router.get("/api/transmission/latest", response_model=List[TransmissionMetricRecord])
async def get_latest_transmission_metrics():
    """Get latest transmission metrics"""
    try:
        sql = """
        SELECT * FROM v_transmission_latest
        ORDER BY metric_name
        """

        result = db_manager.con.execute(sql).fetchall()
        columns = [desc[0] for desc in db_manager.con.description]
        records = [dict(zip(columns, row)) for row in result]

        return [TransmissionMetricRecord(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching latest transmission metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/transmission/timeseries", response_model=List[TransmissionMetricRecord])
async def get_transmission_timeseries(
    metric_name: str = Query(..., description="Metric name to fetch"),
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD format"),
    limit: Optional[int] = Query(None, description="Return up to N most recent points"),
):
    """Get transmission metric time series"""
    try:
        records = db_manager.get_transmission_metrics(
            metric_name=metric_name,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

        return [TransmissionMetricRecord(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching transmission timeseries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/transmission/alerts", response_model=List[TransmissionAlertRecord])
async def get_transmission_alerts(
    limit: int = Query(100, description="Number of recent alerts to return"),
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD format")
):
    """Get transmission alerts"""
    try:
        records = db_manager.get_transmission_alerts(
            alert_type=alert_type,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )

        return [TransmissionAlertRecord(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching transmission alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/transmission/score-summary", response_model=TransmissionScoreSummary)
async def get_transmission_score_summary(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
):
    """
    Summarize the computed transmission_score distribution over a date range.
    Useful for calibration / academic sanity checks (quantiles, bounds, sample size).
    """
    try:
        rows = db_manager.con.execute(
            """
            SELECT metric_value
            FROM transmission_daily_metrics
            WHERE metric_name = 'transmission_score'
              AND metric_value IS NOT NULL
              AND date >= ? AND date <= ?
            ORDER BY date
            """,
            [start_date, end_date],
        ).fetchall()

        values = [float(r[0]) for r in rows if r and r[0] is not None]
        if not values:
            return TransmissionScoreSummary(start_date=start_date, end_date=end_date, n=0)

        values_sorted = sorted(values)

        def quantile(q: float) -> float:
            if q <= 0:
                return values_sorted[0]
            if q >= 1:
                return values_sorted[-1]
            pos = (len(values_sorted) - 1) * q
            lo = int(pos)
            hi = min(lo + 1, len(values_sorted) - 1)
            w = pos - lo
            return values_sorted[lo] * (1 - w) + values_sorted[hi] * w

        return TransmissionScoreSummary(
            start_date=start_date,
            end_date=end_date,
            n=len(values_sorted),
            min=values_sorted[0],
            max=values_sorted[-1],
            p20=quantile(0.20),
            p40=quantile(0.40),
            p50=quantile(0.50),
            p60=quantile(0.60),
            p80=quantile(0.80),
        )
    except Exception as e:
        logger.error(f"Error summarizing transmission score: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/transmission/coverage", response_model=TransmissionCoverageSummary)
async def get_transmission_coverage(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
):
    """
    Coverage diagnostics for the transmission score across a date range.
    Counts days where each component exists (non-null) and days where a score is computable.
    """
    try:
        # Components we consider in the composite (keys stored in transmission_daily_metrics)
        components = [
            "level_10y_zscore",
            "slope_10y_2y_zscore",
            "ib_on_zscore_20d",
            "auction_btc_daily_median_zscore_60d",
            "secondary_value_total_5d_zscore",
            "policy_spread_ib_on_zscore_60d",
        ]

        date_count = db_manager.con.execute(
            """
            SELECT COUNT(DISTINCT date)
            FROM transmission_daily_metrics
            WHERE date >= ? AND date <= ?
            """,
            [start_date, end_date],
        ).fetchone()[0]

        score_computable = db_manager.con.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT
                    date,
                    SUM(CASE WHEN metric_name IN (
                        'level_10y_zscore',
                        'slope_10y_2y_zscore',
                        'ib_on_zscore_20d',
                        'auction_btc_daily_median_zscore_60d',
                        'secondary_value_total_5d_zscore',
                        'policy_spread_ib_on_zscore_60d'
                    ) AND metric_value IS NOT NULL THEN 1 ELSE 0 END) AS k
                FROM transmission_daily_metrics
                WHERE date >= ? AND date <= ?
                GROUP BY date
            ) t
            WHERE k >= 3
            """,
            [start_date, end_date],
        ).fetchone()[0]

        by_component: dict[str, int] = {}
        for comp in components:
            by_component[comp] = db_manager.con.execute(
                """
                SELECT COUNT(DISTINCT date)
                FROM transmission_daily_metrics
                WHERE metric_name = ? AND metric_value IS NOT NULL
                  AND date >= ? AND date <= ?
                """,
                [comp, start_date, end_date],
            ).fetchone()[0]

        return TransmissionCoverageSummary(
            start_date=start_date,
            end_date=end_date,
            dates_total=int(date_count or 0),
            score_computable=int(score_computable or 0),
            by_component=by_component,
        )
    except Exception as e:
        logger.error(f"Error fetching transmission coverage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/transmission/progress", response_model=TransmissionProgressSummary)
async def get_transmission_progress(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
):
    """
    Progress helper for transmission backfill:
    - source_dates_total: union of dates available in core source tables
    - score_computed_dates: dates where transmission_score exists in DB
    """
    try:
        source_dates_total = db_manager.con.execute(
            """
            WITH dates AS (
                SELECT date FROM gov_yield_curve
                UNION
                SELECT date FROM interbank_rates
                UNION
                SELECT date FROM gov_auction_results
                UNION
                SELECT date FROM gov_secondary_trading
                UNION
                SELECT date FROM policy_rates
            )
            SELECT COUNT(DISTINCT date)
            FROM dates
            WHERE date >= ? AND date <= ?
            """,
            [start_date, end_date],
        ).fetchone()[0]

        score_computed_dates = db_manager.con.execute(
            """
            SELECT COUNT(DISTINCT date)
            FROM transmission_daily_metrics
            WHERE metric_name = 'transmission_score'
              AND metric_value IS NOT NULL
              AND date >= ? AND date <= ?
            """,
            [start_date, end_date],
        ).fetchone()[0]

        score_attempted_dates = db_manager.con.execute(
            """
            SELECT COUNT(DISTINCT date)
            FROM transmission_daily_metrics
            WHERE metric_name = 'transmission_score'
              AND date >= ? AND date <= ?
            """,
            [start_date, end_date],
        ).fetchone()[0]

        return TransmissionProgressSummary(
            start_date=start_date,
            end_date=end_date,
            source_dates_total=int(source_dates_total or 0),
            score_attempted_dates=int(score_attempted_dates or 0),
            score_computed_dates=int(score_computed_dates or 0),
        )
    except Exception as e:
        logger.error(f"Error fetching transmission progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Transmission causality (lead-lag / Granger / VAR)
@router.get("/api/transmission/causality/series", response_model=List[CausalitySeriesInfo])
async def get_causality_series_catalog():
    """List available series IDs for causality/lead-lag analysis."""
    try:
        from app.analytics.transmission_causality import TransmissionCausality
        engine = TransmissionCausality(db_manager)
        return [CausalitySeriesInfo(**s) for s in engine.list_series()]
    except Exception as e:
        logger.error(f"Error listing causality series: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/transmission/causality/availability", response_model=List[CausalitySeriesCoverage])
async def get_causality_availability(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
):
    """Return per-series coverage summary for a date range."""
    try:
        from app.analytics.transmission_causality import TransmissionCausality, _parse_date
        engine = TransmissionCausality(db_manager)
        start = _parse_date(start_date)
        end = _parse_date(end_date)
        out = []
        for s in engine.list_series():
            cov = engine.series_coverage(s["id"], start, end)
            out.append(CausalitySeriesCoverage(**cov))
        return out
    except Exception as e:
        logger.error(f"Error fetching causality availability: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/transmission/causality/leadlag", response_model=LeadLagResult)
async def get_lead_lag(
    x: str = Query(..., description="X series id"),
    y: str = Query(..., description="Y series id"),
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
    max_lag: int = Query(20, description="Max lag (observations)"),
    diff: bool = Query(True, description="Use first-differences before analysis"),
):
    """Compute lead-lag (cross-correlation) between two series over a date range."""
    try:
        from app.analytics.transmission_causality import TransmissionCausality, _parse_date
        engine = TransmissionCausality(db_manager)
        result = engine.lead_lag(
            x_id=x,
            y_id=y,
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
            max_lag=max_lag,
            diff=diff,
        )
        return LeadLagResult(**result)
    except Exception as e:
        logger.error(f"Error computing lead-lag: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/transmission/causality/granger", response_model=GrangerResult)
async def get_granger(
    cause: str = Query(..., description="Cause series id"),
    effect: str = Query(..., description="Effect series id"),
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
    max_lag: int = Query(5, description="Max lag (observations)"),
    diff: bool = Query(True, description="Use first-differences before analysis"),
):
    """Run Granger causality test (requires statsmodels)."""
    try:
        from app.analytics.transmission_causality import TransmissionCausality, _parse_date
        engine = TransmissionCausality(db_manager)
        result = engine.granger(
            cause_id=cause,
            effect_id=effect,
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
            max_lag=max_lag,
            diff=diff,
        )
        return GrangerResult(**result)
    except Exception as e:
        logger.error(f"Error computing Granger causality: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/transmission/causality/var", response_model=VarIrfResult)
async def get_var_irf(
    variables: str = Query(..., description="Comma-separated series ids (2-6 recommended)"),
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
    max_lag: int = Query(5, description="Max VAR lag (observations)"),
    steps: int = Query(10, description="IRF steps"),
    diff: bool = Query(True, description="Use first-differences before analysis"),
):
    """Fit VAR and return IRF (requires statsmodels)."""
    try:
        from app.analytics.transmission_causality import TransmissionCausality, _parse_date
        engine = TransmissionCausality(db_manager)
        vars_list = [v.strip() for v in variables.split(",") if v.strip()]
        result = engine.var_irf(
            variables=vars_list,
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
            max_lag=max_lag,
            steps=steps,
            diff=diff,
        )
        return VarIrfResult(**result)
    except Exception as e:
        logger.error(f"Error computing VAR/IRF: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/transmission/causality/network", response_model=GrangerNetworkResult)
async def get_granger_network(
    variables: str = Query("yield_10y,slope_10y_2y,auction_btc,secondary_value,ib_on,policy_anchor,us10y", description="Comma-separated series ids"),
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
    max_lag: int = Query(5, description="Max lag (observations)"),
    alpha: float = Query(0.05, description="Significance threshold"),
    diff: bool = Query(True, description="Use first-differences before analysis"),
):
    """Build a directed network from pairwise Granger tests (requires statsmodels)."""
    try:
        from app.analytics.transmission_causality import TransmissionCausality, _parse_date
        engine = TransmissionCausality(db_manager)
        vars_list = [v.strip() for v in variables.split(",") if v.strip()]
        result = engine.network_granger(
            variables=vars_list,
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
            max_lag=max_lag,
            alpha=alpha,
            diff=diff,
        )
        return GrangerNetworkResult(**result)
    except Exception as e:
        logger.error(f"Error computing Granger network: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/transmission/compute")
async def compute_transmission_metrics(
    target_date: str = Query(..., description="Target date in YYYY-MM-DD format")
):
    """Compute transmission metrics for a specific date"""
    from app.analytics.transmission import TransmissionAnalytics
    from datetime import datetime

    try:
        target = datetime.strptime(target_date, "%Y-%m-%d").date()

        analytics = TransmissionAnalytics(db_manager)
        metrics, alerts = analytics.compute_daily_metrics(target)

        # Insert metrics
        db_manager.insert_transmission_metrics(target_date, metrics)

        # Insert alerts
        if alerts:
            db_manager.insert_transmission_alerts(target_date, alerts)

        return {
            "status": "completed",
            "date": target_date,
            "metrics_count": len(metrics),
            "alerts_count": len(alerts)
        }
    except Exception as e:
        logger.error(f"Error computing transmission metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/transmission/compute-range", response_model=TransmissionComputeRangeResult)
async def compute_transmission_metrics_range(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
    max_dates: int = Query(2000, description="Safety limit on number of dates to compute"),
    skip_existing: bool = Query(True, description="Skip dates that already have transmission_score computed"),
):
    """
    Compute transmission metrics for a date range, iterating only over dates that
    actually exist in source tables (union of dates across core datasets).
    This maximizes reuse of historical data even if a provider (e.g., interbank) lacks backfill.
    """
    from app.analytics.transmission import TransmissionAnalytics
    from datetime import datetime

    try:
        # Validate dates
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")

        if max_dates <= 0:
            raise HTTPException(status_code=400, detail="max_dates must be > 0")

        sql_total = """
        WITH dates AS (
            SELECT date FROM gov_yield_curve
            UNION
            SELECT date FROM interbank_rates
            UNION
            SELECT date FROM gov_auction_results
            UNION
            SELECT date FROM gov_secondary_trading
            UNION
            SELECT date FROM policy_rates
        )
        SELECT COUNT(DISTINCT date)
        FROM dates
        WHERE date >= ? AND date <= ?
        """
        total_dates = db_manager.con.execute(sql_total, [start_date, end_date]).fetchone()[0]

        sql_targets = """
        WITH dates AS (
            SELECT date FROM gov_yield_curve
            UNION
            SELECT date FROM interbank_rates
            UNION
            SELECT date FROM gov_auction_results
            UNION
            SELECT date FROM gov_secondary_trading
            UNION
            SELECT date FROM policy_rates
        ),
        targets AS (
            SELECT DISTINCT date
            FROM dates
            WHERE date >= ? AND date <= ?
        ),
        existing AS (
            SELECT DISTINCT date
            FROM transmission_daily_metrics
            WHERE metric_name = 'transmission_score'
              AND date >= ? AND date <= ?
        )
        SELECT t.date
        FROM targets t
        LEFT JOIN existing e ON t.date = e.date
        WHERE (? = FALSE) OR e.date IS NULL
        ORDER BY t.date
        """
        date_rows = db_manager.con.execute(
            sql_targets,
            [start_date, end_date, start_date, end_date, bool(skip_existing)],
        ).fetchall()
        compute_dates_all = [r[0] for r in date_rows if r and r[0] is not None]

        pending_dates = len(compute_dates_all)
        compute_dates = compute_dates_all[: int(max_dates)]

        analytics = TransmissionAnalytics(db_manager)
        failures: list[dict] = []
        metrics_rows = 0
        alerts_rows = 0

        for d in compute_dates:
            try:
                metrics, alerts = analytics.compute_daily_metrics(d)
                db_manager.insert_transmission_metrics(d.strftime("%Y-%m-%d"), metrics)
                metrics_rows += len(metrics)
                if alerts:
                    db_manager.insert_transmission_alerts(d.strftime("%Y-%m-%d"), alerts)
                    alerts_rows += len(alerts)
            except Exception as e:
                failures.append({"date": d.isoformat(), "error": str(e)})

        processed = len(compute_dates)
        failed = len(failures)
        succeeded = processed - failed

        return TransmissionComputeRangeResult(
            start_date=start_date,
            end_date=end_date,
            max_dates=int(max_dates),
            skip_existing=bool(skip_existing),
            total_dates=int(total_dates or 0),
            pending_dates=int(pending_dates),
            processed=processed,
            succeeded=succeeded,
            failed=failed,
            metrics_rows=metrics_rows,
            alerts_rows=alerts_rows,
            failures=failures,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error computing transmission metrics range: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Daily snapshot endpoints
@router.get("/api/snapshot/today")
async def get_today_snapshot_json(
    target_date: Optional[str] = Query(None, description="Target date in YYYY-MM-DD format (default: today)")
):
    """Get daily snapshot as JSON"""
    from app.analytics.snapshot import DailySnapshotGenerator
    from datetime import datetime

    try:
        if target_date:
            target = datetime.strptime(target_date, "%Y-%m-%d").date()
        else:
            target = date.today()

        generator = DailySnapshotGenerator(db_manager)
        snapshot = generator.generate_snapshot(target)

        return snapshot
    except Exception as e:
        logger.error(f"Error generating snapshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Stress analytics endpoints
class BondYStressRecord(BaseModel):
    date: date
    stress_index: Optional[float]
    regime_bucket: Optional[str]
    driver_json: str
    computed_at: datetime


class GlobalRateRecord(BaseModel):
    date: date
    series_id: str
    series_name: str
    value: Optional[float]
    source: str
    fetched_at: datetime


@router.get("/api/stress/latest", response_model=List[BondYStressRecord])
async def get_latest_stress():
    """Get latest BondY stress index"""
    try:
        records = db_manager.get_bondy_stress(limit=1)
        return [BondYStressRecord(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching latest stress: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/stress/timeseries", response_model=List[BondYStressRecord])
async def get_stress_timeseries(
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD format")
):
    """Get BondY stress time series"""
    try:
        records = db_manager.get_bondy_stress(
            start_date=start_date,
            end_date=end_date
        )
        return [BondYStressRecord(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching stress timeseries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/stress/drivers")
async def get_stress_drivers(
    date: str = Query(..., description="Date in YYYY-MM-DD format")
):
    """Get top stress drivers for a specific date"""
    try:
        records = db_manager.get_bondy_stress(
            start_date=date,
            end_date=date
        )

        if not records:
            raise HTTPException(status_code=404, detail="No stress data found for this date")

        record = records[0]
        import json
        drivers = json.loads(record['driver_json']) if record.get('driver_json') else []

        return {
            'date': date,
            'stress_index': record['stress_index'],
            'regime_bucket': record['regime_bucket'],
            'drivers': drivers
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching stress drivers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Global rates endpoints (FRED)
@router.get("/api/global/rates", response_model=List[GlobalRateRecord])
async def get_global_rates(
    series_id: Optional[str] = Query(None, description="FRED series id (e.g., DGS10)"),
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD format"),
    limit: Optional[int] = Query(None, description="Return up to N most recent points"),
):
    """Get global rates time series (from global_rates_daily)"""
    try:
        records = db_manager.get_global_rates(
            series_id=series_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        return [GlobalRateRecord(**r) for r in records]
    except Exception as e:
        logger.error(f"Error fetching global rates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/stress/compute")
async def compute_stress_metrics(
    target_date: str = Query(..., description="Target date in YYYY-MM-DD format")
):
    """Compute BondY stress metrics for a specific date"""
    from app.analytics.stress_model import BondYStressModel
    from datetime import datetime
    import json

    try:
        target = datetime.strptime(target_date, "%Y-%m-%d").date()

        stress_model = BondYStressModel(db_manager)
        stress_index, regime_bucket, components = stress_model.compute_stress_index(target)

        # Insert stress record
        driver_json = json.dumps(components.get('drivers', []))
        db_manager.insert_bondy_stress(
            target_date,
            stress_index,
            regime_bucket,
            driver_json
        )

        return {
            "status": "completed",
            "date": target_date,
            "stress_index": stress_index,
            "regime_bucket": regime_bucket,
            "drivers_count": len(components.get('drivers', []))
        }
    except Exception as e:
        logger.error(f"Error computing stress metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/stress/compute-range")
async def compute_stress_metrics_range(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
    max_dates: int = Query(300, description="Process up to N dates per request (batching)"),
    skip_existing: bool = Query(True, description="Skip dates already present in bondy_stress_daily"),
):
    """
    Compute BondY stress index for a date range (batch).

    Notes:
    - Stress depends on transmission metrics. We therefore iterate over dates that already have
      transmission_daily_metrics available within the range.
    - Designed to be called repeatedly (like transmission compute-range) until pending=0.
    """
    from app.analytics.stress_model import BondYStressModel
    from datetime import datetime
    import json

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        if start > end:
            raise HTTPException(status_code=400, detail="start_date must be <= end_date")

        # Candidate dates: dates with a *transmission_score* metric.
        # Rationale:
        # - Stress index is defined as a composite anchored by Transmission score.
        # - Without transmission_score, stress computation often returns None and would
        #   remain "pending" forever (since we won't insert a record).
        cand_rows = db_manager.con.execute(
            """
            SELECT DISTINCT date
            FROM transmission_daily_metrics
            WHERE metric_name = 'transmission_score'
              AND metric_value IS NOT NULL
              AND date >= ? AND date <= ?
            ORDER BY date
            """,
            [start.isoformat(), end.isoformat()],
        ).fetchall()
        candidate_dates = [r[0] for r in cand_rows if r and r[0] is not None]

        existing_dates: set[str] = set()
        if skip_existing and candidate_dates:
            rows = db_manager.con.execute(
                """
                SELECT date
                FROM bondy_stress_daily
                WHERE date >= ? AND date <= ?
                """,
                [start.isoformat(), end.isoformat()],
            ).fetchall()
            existing_dates = {str(r[0]) for r in rows if r and r[0] is not None}

        pending = [d for d in candidate_dates if str(d) not in existing_dates]

        to_process = pending[: max(0, int(max_dates))]
        stress_model = BondYStressModel(db_manager)

        succeeded = 0
        skipped = 0
        failed = 0
        failures: list[dict] = []

        for d in to_process:
            d_str = str(d)
            try:
                stress_index, regime_bucket, components = stress_model.compute_stress_index(d)
                if stress_index is None or regime_bucket is None:
                    skipped += 1
                    continue

                driver_json = json.dumps((components or {}).get("drivers", []))
                db_manager.insert_bondy_stress(
                    d_str,
                    stress_index,
                    regime_bucket,
                    driver_json,
                )
                succeeded += 1
            except Exception as e:
                failed += 1
                failures.append({"date": d_str, "error": str(e)})

        remaining = len(pending) - len(to_process)
        return {
            "start_date": start_date,
            "end_date": end_date,
            "max_dates": int(max_dates),
            "skip_existing": bool(skip_existing),
            "total_candidate_dates": len(candidate_dates),
            "pending_dates": len(pending),
            "processed": len(to_process),
            "succeeded": int(succeeded),
            "skipped": int(skipped),
            "failed": int(failed),
            "remaining": int(remaining),
            "failures": failures[:20],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error computing stress range: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# PDF report endpoints
@router.get("/api/report/daily")
async def get_daily_pdf_metadata(
    target_date: Optional[str] = Query(None, description="Target date in YYYY-MM-DD format (default: today)")
):
    """Get daily PDF report metadata"""
    from datetime import datetime
    from pathlib import Path

    try:
        if target_date:
            target = datetime.strptime(target_date, "%Y-%m-%d").date()
        else:
            target = date.today()

        # Check if PDF exists
        pdf_path = Path(f"data/reports/daily_{target.strftime('%Y%m%d')}.pdf")

        if pdf_path.exists():
            return {
                "date": target_date,
                "file_exists": True,
                "file_size": pdf_path.stat().st_size,
                "generated_at": datetime.fromtimestamp(pdf_path.stat().st_mtime).isoformat()
            }
        else:
            return {
                "date": target_date,
                "file_exists": False,
                "message": "PDF not yet generated. Generate with GET /report/daily.pdf"
            }

    except Exception as e:
        logger.error(f"Error getting PDF metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Notification Channels endpoints
@router.get("/api/admin/notifications")
async def get_notification_channels():
    """Get all notification channels"""
    try:
        channels = db_manager.get_notification_channels(enabled_only=False)

        # Parse config_json for each channel
        for channel in channels:
            import json
            if channel.get('config_json'):
                try:
                    channel['config'] = json.loads(channel['config_json'])
                    # Remove sensitive fields from response
                    if channel['channel_type'] == 'email' and 'password' in channel['config']:
                        channel['config']['password'] = '******'
                except json.JSONDecodeError:
                    channel['config'] = {}
            else:
                channel['config'] = {}

        return channels

    except Exception as e:
        logger.error(f"Error fetching notification channels: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/notifications/email")
async def create_email_channel(
    name: str = Query(..., description="Channel name"),
    smtp_server: str = Query(..., description="SMTP server address"),
    smtp_port: int = Query(587, description="SMTP port"),
    from_addr: str = Query(..., description="From email address"),
    to_addr: str = Query(..., description="To email address"),
    username: Optional[str] = Query(None, description="SMTP username"),
    password: Optional[str] = Query(None, description="SMTP password"),
    enabled: bool = Query(False, description="Enable channel immediately")
):
    """Create email notification channel"""
    try:
        import json

        config = {
            'smtp_server': smtp_server,
            'smtp_port': smtp_port,
            'from_addr': from_addr,
            'to_addr': to_addr
        }
        if username:
            config['username'] = username
        if password:
            config['password'] = password

        sql = """
        INSERT INTO notification_channels (channel_type, enabled, config_json)
        VALUES ('email', ?, ?)
        RETURNING id
        """

        result = db_manager.con.execute(sql, [enabled, json.dumps(config)]).fetchone()

        logger.info(f"Created email notification channel {result[0]}")
        return {'status': 'success', 'channel_id': result[0]}

    except Exception as e:
        logger.error(f"Error creating email channel: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/notifications/webhook")
async def create_webhook_channel(
    name: str = Query(..., description="Channel name"),
    url: str = Query(..., description="Webhook URL"),
    method: str = Query("POST", description="HTTP method (POST or GET)"),
    headers: Optional[str] = Query(None, description="JSON string of HTTP headers"),
    enabled: bool = Query(False, description="Enable channel immediately")
):
    """Create webhook notification channel"""
    try:
        import json

        config = {
            'url': url,
            'method': method.upper()
        }
        if headers:
            try:
                config['headers'] = json.loads(headers)
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"Invalid JSON in headers: {e}")

        sql = """
        INSERT INTO notification_channels (channel_type, enabled, config_json)
        VALUES ('webhook', ?, ?)
        RETURNING id
        """

        result = db_manager.con.execute(sql, [enabled, json.dumps(config)]).fetchone()

        logger.info(f"Created webhook notification channel {result[0]}")
        return {'status': 'success', 'channel_id': result[0]}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating webhook channel: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/notifications/{channel_id}/toggle")
async def toggle_notification_channel(
    channel_id: int,
    enabled: bool = Query(..., description="Enable or disable channel")
):
    """Toggle notification channel enabled status"""
    try:
        sql = """
        UPDATE notification_channels
        SET enabled = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """

        db_manager.con.execute(sql, [enabled, channel_id])

        return {
            'status': 'success',
            'channel_id': channel_id,
            'enabled': enabled
        }

    except Exception as e:
        logger.error(f"Error toggling notification channel: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/admin/notifications/{channel_id}")
async def delete_notification_channel(channel_id: int):
    """Delete notification channel"""
    try:
        sql = "DELETE FROM notification_channels WHERE id = ?"
        db_manager.con.execute(sql, [channel_id])

        return {'status': 'success', 'channel_id': channel_id}

    except Exception as e:
        logger.error(f"Error deleting notification channel: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/admin/notifications/events")
async def get_notification_events(
    limit: int = Query(50, description="Number of recent events"),
    alert_code: Optional[str] = Query(None, description="Filter by alert code"),
    channel_id: Optional[int] = Query(None, description="Filter by channel ID")
):
    """Get recent notification events"""
    try:
        sql = """
        SELECT ne.*, nc.channel_type
        FROM notification_events ne
        LEFT JOIN notification_channels nc ON ne.channel_id = nc.id
        WHERE 1=1
        """

        params = []
        if alert_code:
            sql += " AND ne.alert_code = ?"
            params.append(alert_code)
        if channel_id:
            sql += " AND ne.channel_id = ?"
            params.append(channel_id)

        sql += " ORDER BY ne.created_at DESC LIMIT ?"
        params.append(limit)

        results = db_manager.con.execute(sql, params).fetchall()

        events = []
        for row in results:
            columns = [desc[0] for desc in db_manager.con.description]
            event = dict(zip(columns, row))
            # Convert to string for JSON serialization
            for key, value in event.items():
                if value is not None and not isinstance(value, (str, int, float, bool, dict, list)):
                    event[key] = str(value)
            events.append(event)

        return events

    except Exception as e:
        logger.error(f"Error fetching notification events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Alert Thresholds endpoints
@router.get("/api/admin/alerts")
async def get_alert_thresholds():
    """Get all alert thresholds"""
    try:
        sql = """
        SELECT alert_code, enabled, severity, params_json, updated_at
        FROM alert_thresholds
        ORDER BY alert_code
        """

        results = db_manager.con.execute(sql).fetchall()

        thresholds = []
        for row in results:
            import json
            alert_code, enabled, severity, params_json, updated_at = row
            thresholds.append({
                'alert_code': alert_code,
                'enabled': bool(enabled),
                'severity': severity,
                'params': json.loads(params_json) if params_json else {},
                'updated_at': str(updated_at) if updated_at else None
            })

        return thresholds

    except Exception as e:
        logger.error(f"Error fetching alert thresholds: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/alerts/{alert_code}")
async def upsert_alert_threshold(
    alert_code: str,
    enabled: bool = Query(..., description="Enable/disable alert"),
    severity: str = Query(..., description="Severity level (HIGH, MEDIUM, LOW)"),
    params: Optional[str] = Query(None, description="JSON string of parameters")
):
    """Insert or update an alert threshold"""
    try:
        import json

        # Parse params if provided
        params_dict = {}
        if params:
            try:
                params_dict = json.loads(params)
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"Invalid JSON in params: {e}")

        # Upsert threshold
        db_manager.upsert_alert_threshold(
            alert_code=alert_code,
            enabled=enabled,
            severity=severity,
            params=params_dict
        )

        return {
            'status': 'success',
            'alert_code': alert_code,
            'enabled': enabled,
            'severity': severity,
            'params': params_dict
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error upserting alert threshold: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/alerts/test")
async def test_alert_threshold(
    alert_code: str = Query(..., description="Alert code to test"),
    metrics: Optional[str] = Query(None, description="JSON string of metrics to test"),
    custom_params: Optional[str] = Query(None, description="JSON string of custom parameters")
):
    """Test an alert threshold with given metrics"""
    try:
        import json
        from app.analytics.alert_engine import AlertEngine

        # Parse metrics
        if metrics:
            try:
                metrics_dict = json.loads(metrics)
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"Invalid JSON in metrics: {e}")
        else:
            # Use latest available metrics
            latest = db_manager.get_transmission_metrics(
                start_date=str(date.today()),
                end_date=str(date.today())
            )
            metrics_dict = {m['metric_name']: m['metric_value'] for m in latest if m['metric_value'] is not None}

        # Parse custom params
        custom_params_dict = None
        if custom_params:
            try:
                custom_params_dict = json.loads(custom_params)
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"Invalid JSON in custom_params: {e}")

        # Test threshold
        engine = AlertEngine(db_manager)
        result = engine.test_threshold(alert_code, metrics_dict, custom_params_dict)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing alert threshold: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/alerts/reload")
async def reload_alert_thresholds():
    """Force reload alert thresholds from database (clears cache)"""
    try:
        from app.analytics.alert_engine import AlertEngine

        engine = AlertEngine(db_manager)
        engine._load_thresholds(force_reload=True)

        return {
            'status': 'success',
            'message': 'Alert thresholds reloaded from database'
        }

    except Exception as e:
        logger.error(f"Error reloading alert thresholds: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Data Quality endpoints
@router.get("/api/admin/quality/latest")
async def get_dq_latest(date: str = Query(None, description="Target date (YYYY-MM-DD), defaults to today")):
    """Get latest DQ status for a date"""
    try:
        from app.quality import DataQualityRunner
        from datetime import date as date_type

        target_date = date_type.fromisoformat(date) if date else date_type.today()

        runner = DataQualityRunner(db_manager)
        dq_status = runner.get_dq_status_for_date(target_date)

        if not dq_status:
            # No DQ run exists for this date
            return {
                'target_date': str(target_date),
                'status': 'NOT_RUN',
                'message': 'No DQ run found for this date'
            }

        return dq_status

    except Exception as e:
        logger.error(f"Error getting DQ latest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/admin/quality/results")
async def get_dq_results(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    dataset_id: Optional[str] = Query(None, description="Filter by dataset ID"),
    severity: Optional[str] = Query(None, description="Filter by severity (INFO/WARN/ERROR)"),
    limit: int = Query(100, description="Max results to return")
):
    """Get DQ results with filters"""
    try:
        from app.quality import DataQualityRunner
        from datetime import date as date_type

        runner = DataQualityRunner(db_manager)

        start = date_type.fromisoformat(start_date) if start_date else None
        end = date_type.fromisoformat(end_date) if end_date else None

        results = runner.get_dq_results(
            start_date=start,
            end_date=end,
            dataset_id=dataset_id,
            severity=severity,
            limit=limit
        )

        return results

    except Exception as e:
        logger.error(f"Error getting DQ results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/quality/run")
async def run_dq(
    date: str = Query(..., description="Target date (YYYY-MM-DD)"),
    datasets: Optional[str] = Query(None, description="Comma-separated list of datasets"),
    override_block: bool = Query(False, description="Override ERROR blocks")
):
    """Run DQ checks for a specific date"""
    try:
        from app.quality import DataQualityRunner
        from datetime import date as date_type

        target_date = date_type.fromisoformat(date)
        dataset_list = datasets.split(',') if datasets else None

        runner = DataQualityRunner(db_manager)
        result = runner.run_dq_for_date(
            target_date=target_date,
            datasets=dataset_list,
            override_block=override_block
        )

        return result

    except Exception as e:
        logger.error(f"Error running DQ: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/quality/run-range")
async def run_dq_range(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    datasets: Optional[str] = Query(None, description="Comma-separated list of datasets"),
    override_block: bool = Query(False, description="Override ERROR blocks")
):
    """Run DQ checks for a date range"""
    try:
        from app.quality import DataQualityRunner
        from datetime import date as date_type, timedelta

        start = date_type.fromisoformat(start_date)
        end = date_type.fromisoformat(end_date)
        dataset_list = datasets.split(',') if datasets else None

        runner = DataQualityRunner(db_manager)

        results = []
        current = start
        while current <= end:
            result = runner.run_dq_for_date(
                target_date=current,
                datasets=dataset_list,
                override_block=override_block
            )
            results.append({
                'date': str(current),
                'result': result
            })
            current += timedelta(days=1)

        return {
            'start_date': str(start),
            'end_date': str(end),
            'runs': results
        }

    except Exception as e:
        logger.error(f"Error running DQ range: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Ops endpoints
@router.post("/api/admin/ops/backup")
async def create_backup():
    """Create a database backup"""
    try:
        from app.ops import OpsManager

        # Get DB path from db_manager
        db_path = str(db_manager.db_path) if hasattr(db_manager, 'db_path') else 'data/bond_lab.db'

        ops = OpsManager(db_path)
        backup_path = ops.backup()

        return {
            'status': 'success',
            'backup_path': backup_path
        }

    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/admin/ops/backups")
async def list_backups():
    """List all backups"""
    try:
        from app.ops import OpsManager

        db_path = str(db_manager.db_path) if hasattr(db_manager, 'db_path') else 'data/bond_lab.db'

        ops = OpsManager(db_path)
        backups = ops.list_backups()

        return backups

    except Exception as e:
        logger.error(f"Error listing backups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/ops/verify-backup")
async def verify_backup(backup_path: str = Query(..., description="Path to backup file")):
    """Verify a backup file"""
    try:
        from app.ops import OpsManager

        db_path = str(db_manager.db_path) if hasattr(db_manager, 'db_path') else 'data/bond_lab.db'

        ops = OpsManager(db_path)
        verification = ops.verify_backup(backup_path)

        return verification

    except Exception as e:
        logger.error(f"Error verifying backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/ops/restore")
async def restore_backup(
    backup_path: str = Query(..., description="Path to backup file"),
    confirm: bool = Query(False, description="Confirmation flag")
):
    """Restore database from backup (requires ALLOW_RESTORE=true)"""
    try:
        from app.ops import OpsManager

        if not confirm:
            raise HTTPException(
                status_code=400,
                detail="Set confirm=true to proceed with restore operation"
            )

        db_path = str(db_manager.db_path) if hasattr(db_manager, 'db_path') else 'data/bond_lab.db'

        ops = OpsManager(db_path)
        ops.restore(backup_path, require_confirmation=True)

        return {
            'status': 'success',
            'message': f'Database restored from {backup_path}'
        }

    except RuntimeError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error restoring backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Monitoring endpoints
@router.get("/api/admin/monitoring/summary")
async def get_monitoring_summary():
    """Get monitoring summary - pipeline status, SLO metrics"""
    try:
        # Get last ingest run
        ingest_result = db_manager.con.execute("""
            SELECT
                id,
                provider,
                status,
                started_at,
                ended_at,
                CASE
                    WHEN ended_at IS NULL THEN NULL
                    ELSE datediff('second', started_at, ended_at)
                END as duration_seconds
            FROM ingest_runs
            ORDER BY started_at DESC
            LIMIT 1
        """).fetchone()

        last_ingest = {
            'run_id': ingest_result[0],
            'provider': ingest_result[1],
            'status': ingest_result[2],
            'started_at': str(ingest_result[3]),
            'duration_seconds': ingest_result[5],
        } if ingest_result else None

        # Get last DQ status
        dq_result = db_manager.con.execute("""
            SELECT id, status, run_at, target_date
            FROM dq_runs
            ORDER BY run_at DESC
            LIMIT 1
        """).fetchone()

        last_dq = {
            'run_id': dq_result[0],
            'status': dq_result[1],
            'run_at': str(dq_result[2]),
            'target_date': str(dq_result[3]) if dq_result[3] is not None else None,
        } if dq_result else None

        # Calculate SLO metrics (last 30 days)
        slo_result = db_manager.con.execute("""
            WITH date_range AS (
                SELECT DISTINCT target_date as date FROM dq_runs
                WHERE target_date >= current_date - INTERVAL 30 DAY
            ),
            snapshot_dates AS (
                SELECT DISTINCT date FROM daily_snapshots
                WHERE date >= current_date - INTERVAL 30 DAY
            )
            SELECT
                (SELECT COUNT(*) FROM date_range) as total_days,
                (SELECT COUNT(*) FROM date_range JOIN dq_runs ON date_range.date = dq_runs.target_date WHERE dq_runs.status = 'FAIL') as dq_failed_days,
                (SELECT COUNT(*) FROM snapshot_dates) as snapshot_days
        """).fetchone()

        slo = {
            'total_days': slo_result[0],
            'dq_failed_days': slo_result[1],
            'snapshot_days': slo_result[2],
            'dq_success_rate': round((1 - (slo_result[1] / slo_result[0])) * 100, 1) if slo_result[0] > 0 else None,
            'snapshot_coverage': round((slo_result[2] / slo_result[0]) * 100, 1) if slo_result[0] > 0 else None
        }

        return {
            'last_ingest': last_ingest,
            'last_dq': last_dq,
            'slo_30d': slo
        }

    except Exception as e:
        logger.error(f"Error getting monitoring summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/admin/monitoring/providers")
async def get_provider_monitoring():
    """Get provider reliability metrics (30 days)"""
    try:
        # Provider success rates
        providers_result = db_manager.con.execute("""
            SELECT provider, status, COUNT(*) as count
            FROM ingest_runs
            WHERE started_at >= current_timestamp - INTERVAL 30 DAY
            GROUP BY provider, status
            ORDER BY provider, status
        """).fetchall()

        providers = {}
        for row in providers_result:
            provider, status, count = row
            if provider not in providers:
                providers[provider] = {'success': 0, 'error': 0, 'total': 0}
            providers[provider][status.lower() if status.lower() in ['success', 'error'] else 'error'] = count
            providers[provider]['total'] += count

        # Calculate success rates
        for provider in providers:
            p = providers[provider]
            p['success_rate'] = round((p['success'] / p['total']) * 100, 1) if p['total'] > 0 else None

        # Get median latency per provider
        latency_result = db_manager.con.execute("""
            SELECT
                provider,
                AVG(datediff('second', started_at, ended_at)) as avg_duration
            FROM ingest_runs
            WHERE started_at >= current_timestamp - INTERVAL 30 DAY AND ended_at IS NOT NULL
            GROUP BY provider
            ORDER BY avg_duration ASC
        """).fetchall()

        latencies = {row[0]: round(row[1], 2) for row in latency_result}

        return {
            'providers': providers,
            'latencies': latencies,
            'period_days': 30
        }

    except Exception as e:
        logger.error(f"Error getting provider monitoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/admin/monitoring/drift")
async def get_drift_signals():
    """Get recent drift signals from source_fingerprints"""
    try:
        # Get recent fingerprint changes
        drift_result = db_manager.con.execute("""
            SELECT provider, dataset_id,
                   COUNT(DISTINCT fingerprint_hash) as fingerprint_count,
                   MAX(fetched_at) as last_fetched,
                   AVG(parse_rowcount) as avg_rowcount,
                   SUM(CASE WHEN parse_required_fields_ok = FALSE THEN 1 ELSE 0 END) as parse_failures
            FROM source_fingerprints
            WHERE fetched_at >= current_timestamp - INTERVAL 30 DAY
            GROUP BY provider, dataset_id
            HAVING fingerprint_count > 1
            ORDER BY last_fetched DESC
        """).fetchall()

        drifts = []
        for row in drift_result:
            provider, dataset_id, fp_count, last_fetched, avg_rowcount, parse_failures = row
            drifts.append({
                'provider': provider,
                'dataset_id': dataset_id,
                'fingerprint_changes': fp_count - 1,
                'last_fetched': str(last_fetched),
                'avg_rowcount': round(avg_rowcount, 1) if avg_rowcount else None,
                'parse_failures': parse_failures
            })

        return {'drifts': drifts, 'period_days': 30}

    except Exception as e:
        logger.error(f"Error getting drift signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Coverage endpoint (for admin UI)
@router.get("/api/admin/coverage")
async def get_data_coverage():
    """Get data coverage statistics for all tables"""
    try:
        coverage = {}

        tables = [
            'gov_yield_curve',
            'gov_yield_change_stats',
            'interbank_rates',
            'gov_auction_results',
            'gov_secondary_trading',
            'policy_rates'
        ]

        for table in tables:
            try:
                sql = f"""
                SELECT
                    MIN(date) as earliest_date,
                    MAX(date) as latest_date,
                    COUNT(DISTINCT date) as date_count
                FROM {table}
                """

                result = db_manager.con.execute(sql).fetchone()

                if result and result[0]:
                    coverage[table] = {
                        'earliest_date': str(result[0]),
                        'latest_date': str(result[1]),
                        'date_count': result[2],
                        'has_data': True
                    }
                else:
                    coverage[table] = {
                        'earliest_date': None,
                        'latest_date': None,
                        'date_count': 0,
                        'has_data': False
                    }
            except Exception as e:
                logger.debug(f"Error getting coverage for {table}: {e}")
                coverage[table] = {
                    'error': str(e),
                    'has_data': False
                }

        return coverage

    except Exception as e:
        logger.error(f"Error getting data coverage: {e}")
        raise HTTPException(status_code=500, detail=str(e))
