import sqlite3
from typing import Optional, List, Dict, Any
from datetime import datetime
from .settings import get_settings


def get_connection():
    """Get a new SQLite connection."""
    settings = get_settings()
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


REQUIRED_SERIES: list[tuple[str, str, str]] = [
    ("deposit", "deposit_online", "Tiền gửi Online"),
    ("deposit", "deposit_tai_quay", "Tiền gửi Tại quầy"),
    ("loan", "loan_the_chap", "Vay Thế chấp"),
    ("loan", "loan_tin_chap", "Vay Tín chấp"),
]


def seed_required_series() -> dict[str, int]:
    """
    Ensure required series codes exist (idempotent).

    Returns a small summary for logging.
    """
    conn = get_connection()
    cursor = conn.cursor()

    inserted = 0
    for product_group, code, description in REQUIRED_SERIES:
        cursor.execute(
            """
            INSERT OR IGNORE INTO series (product_group, code, description)
            VALUES (?, ?, ?)
            """,
            (product_group, code, description),
        )
        inserted += cursor.rowcount

    conn.commit()
    conn.close()
    return {"inserted": inserted}


def get_health() -> Dict[str, Any]:
    """Check database connection."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_meta_latest() -> Dict[str, Any]:
    """Get latest metadata about sources and observations."""
    conn = get_connection()
    cursor = conn.cursor()

    # Get latest scraped_at for each source URL
    cursor.execute("""
        SELECT url, MAX(scraped_at) as scraped_at
        FROM sources
        GROUP BY url
    """)
    scraped_at_by_url = {row["url"]: row["scraped_at"] for row in cursor.fetchall()}

    # Get overall latest scraped_at
    latest_scraped_at = None
    if scraped_at_by_url:
        latest_scraped_at = max(scraped_at_by_url.values())

    # Get counts
    cursor.execute("SELECT COUNT(*) as count FROM sources")
    sources_count = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM observations")
    observations_count = cursor.fetchone()["count"]

    # Get distinct days overall (Phase 2C: Data Integrity feature)
    try:
        cursor.execute("""
            SELECT COUNT(DISTINCT o.observed_day) as distinct_days
            FROM observations o
            WHERE o.observed_day IS NOT NULL
        """)
        distinct_days_row = cursor.fetchone()
        distinct_days_overall = distinct_days_row["distinct_days"] if distinct_days_row else 0
    except Exception:
        # Fallback if observed_day doesn't exist yet
        distinct_days_overall = 0

    # Check for anomalies (if any source has error or warning flags)
    last_anomaly = None
    cursor.execute("""
        SELECT scraped_at
        FROM sources
        WHERE scraped_at LIKE '%error%' OR scraped_at LIKE '%warning%'
        ORDER BY scraped_at DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    if row:
        last_anomaly = row["scraped_at"]

    conn.close()

    return {
        "scraped_at_by_url": scraped_at_by_url,
        "latest_scraped_at": latest_scraped_at,
        "sources_count": sources_count,
        "observations_count": observations_count,
        "distinct_days_overall": distinct_days_overall,
        "last_anomaly": last_anomaly
    }


def get_banks() -> List[str]:
    """Get all unique bank names."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT name
        FROM banks
        ORDER BY name ASC
    """)
    banks = [row["name"] for row in cursor.fetchall()]

    conn.close()
    return banks


def get_series() -> List[Dict[str, Any]]:
    """Get all series."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT code, product_group, description
        FROM series
        ORDER BY code ASC
    """)
    series_list = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return series_list


def get_latest_rates(series_code: str, term_months: Optional[int] = None, sort: str = "rate_desc") -> List[Dict[str, Any]]:
    """
    Get latest rates for a specific series.

    Args:
        series_code: Series code (e.g., deposit_online, loan_the_chap)
        term_months: Required for deposit series (e.g., 1, 6, 12)
        sort: Sort order (rate_desc, rate_asc, bank_asc)
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Validate series_code
    cursor.execute("SELECT code FROM series WHERE code = ?", (series_code,))
    if not cursor.fetchone():
        conn.close()
        raise ValueError(f"Invalid series_code: {series_code}")

    # For deposit series, require term_months
    if series_code.startswith("deposit_") and term_months is None:
        conn.close()
        raise ValueError(f"term_months is required for deposit series (got series_code={series_code})")

    # For loan series, term_months should be None
    if series_code.startswith("loan_") and term_months is not None:
        conn.close()
        raise ValueError(f"term_months should not be provided for loan series (got series_code={series_code})")

    # Build query - use v_latest_observations_merged for canonical multi-source data
    query = """
        SELECT
            bank_name,
            series_code,
            term_months,
            term_label,
            rate_pct,
            rate_min_pct,
            rate_max_pct,
            raw_value,
            scraped_at,
            source_url,
            source_priority
        FROM v_latest_observations_merged
        WHERE series_code = ?
    """
    params = [series_code]

    if term_months is not None:
        query += " AND term_months = ?"
        params.append(term_months)

    # Add sorting
    if sort == "rate_desc":
        query += " ORDER BY rate_pct DESC"
    elif sort == "rate_asc":
        query += " ORDER BY rate_pct ASC"
    elif sort == "bank_asc":
        query += " ORDER BY bank_name ASC"
    else:
        query += " ORDER BY rate_pct DESC"

    cursor.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return rows


def get_history(bank_name: str, series_code: str, term_months: Optional[int] = None, limit: int = 120) -> Dict[str, Any]:
    """
    Get historical rates for a specific bank and series.

    Args:
        bank_name: Bank name
        series_code: Series code
        term_months: Required for deposit series
        limit: Maximum number of history points to return
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Validate bank_name
    cursor.execute("SELECT id FROM banks WHERE name = ?", (bank_name,))
    if not cursor.fetchone():
        conn.close()
        raise ValueError(f"Bank not found: {bank_name}")

    # Validate series_code and get series_id
    cursor.execute("SELECT id, code FROM series WHERE code = ?", (series_code,))
    series_row = cursor.fetchone()
    if not series_row:
        conn.close()
        raise ValueError(f"Invalid series_code: {series_code}")

    series_id = series_row["id"]

    # For deposit series, require term_months
    if series_code.startswith("deposit_") and term_months is None:
        conn.close()
        raise ValueError(f"term_months is required for deposit series (got series_code={series_code})")

    # For loan series, term_months should be None
    if series_code.startswith("loan_") and term_months is not None:
        conn.close()
        raise ValueError(f"term_months should not be provided for loan series (got series_code={series_code})")

    # Get bank_id
    cursor.execute("SELECT id FROM banks WHERE name = ?", (bank_name,))
    bank_id = cursor.fetchone()["id"]

    # Get term_id if needed
    term_id = None
    if term_months is not None:
        cursor.execute("SELECT id FROM terms WHERE months = ?", (term_months,))
        term_row = cursor.fetchone()
        if not term_row:
            conn.close()
            raise ValueError(f"Term not found: {term_months} months")
        term_id = term_row["id"]

    # Build query - canonical history with priority-based dedup per day
    # Uses ROW_NUMBER() to pick best source per observed_day
    query = """
        WITH ranked_obs AS (
            SELECT
                o.observed_day,
                o.rate_pct,
                o.rate_min_pct,
                o.rate_max_pct,
                s.scraped_at,
                ROW_NUMBER() OVER (
                    PARTITION BY o.observed_day
                    ORDER BY
                        COALESCE(sp.priority, 999) ASC,
                        s.scraped_at DESC,
                        o.id DESC
                ) AS rn
            FROM observations o
            JOIN sources s ON o.source_id = s.id
            LEFT JOIN source_priorities sp ON s.url = sp.url
            WHERE o.bank_id = ?
              AND o.series_id = ?
    """
    params = [bank_id, series_id]

    if term_id is not None:
        query += "              AND o.term_id = ?"
        params.append(term_id)

    query += """
        )
        SELECT
            scraped_at,
            rate_pct,
            rate_min_pct,
            rate_max_pct
        FROM ranked_obs
        WHERE rn = 1
          AND observed_day IS NOT NULL
        ORDER BY scraped_at ASC
        LIMIT ?
    """
    params.append(limit)

    cursor.execute(query, params)
    points = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return {
        "points": points,
        "meta": {
            "bank_name": bank_name,
            "series_code": series_code,
            "term_months": term_months
        }
    }
