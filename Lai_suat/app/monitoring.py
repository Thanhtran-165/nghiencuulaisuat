"""Monitoring and anomaly detection for scraping operations."""

import sqlite3
from typing import Optional, Tuple, Dict, Any
from .utils import logger


def get_latest_extracted_count(
    conn: sqlite3.Connection,
    url: str,
    *,
    exclude_source_id: Optional[int] = None,
) -> Optional[int]:
    """
    Get record_count_extracted from the latest source for a given URL.

    Args:
        conn: SQLite database connection
        url: Source URL to query

    Returns:
        Latest record_count_extracted value or None if no previous source exists
    """
    cursor = conn.cursor()

    # Get the latest source for this URL
    if exclude_source_id is None:
        cursor.execute(
            """
            SELECT record_count_extracted
            FROM sources
            WHERE url = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (url,),
        )
    else:
        cursor.execute(
            """
            SELECT record_count_extracted
            FROM sources
            WHERE url = ? AND id < ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (url, int(exclude_source_id)),
        )

    result = cursor.fetchone()

    if result and result[0] is not None:
        return int(result[0])

    return None


def detect_anomaly(
    prev_count: Optional[int],
    new_count: int,
    threshold: float = 0.30
) -> Tuple[bool, Optional[float]]:
    """
    Detect anomaly by comparing previous and new record counts.

    Anomaly occurs if:
    - prev_count exists and is > 0
    - (prev_count - new_count) / prev_count > threshold

    Args:
        prev_count: Previous record count (can be None)
        new_count: Current record count
        threshold: Anomaly threshold (default 0.30 = 30% drop)

    Returns:
        Tuple of (is_anomaly, drop_ratio)
        - is_anomaly: True if anomaly detected
        - drop_ratio: Drop ratio as float (0.0 to 1.0), or None if prev_count is None/0
    """
    # No previous data to compare
    if prev_count is None:
        return False, None

    # Previous count was zero, can't compute ratio
    if prev_count == 0:
        return False, None

    # Compute drop ratio
    drop_ratio = (prev_count - new_count) / prev_count

    # Anomaly if drop ratio exceeds threshold (strictly greater)
    is_anomaly = drop_ratio > threshold

    return is_anomaly, drop_ratio


def check_anomaly(
    conn: sqlite3.Connection,
    url: str,
    new_count: int,
    threshold: float = 0.30,
    *,
    exclude_source_id: Optional[int] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Check for anomaly by comparing new_count with previous extracted count.

    Args:
        conn: SQLite database connection
        url: Source URL
        new_count: Current record count extracted
        threshold: Anomaly threshold (default 0.30)

    Returns:
        Tuple of (is_anomaly, info_dict)
        - is_anomaly: True if anomaly detected
        - info_dict: Dictionary with prev_count, new_count, drop_ratio, threshold
    """
    # Get previous count
    prev_count = get_latest_extracted_count(conn, url, exclude_source_id=exclude_source_id)

    # Detect anomaly
    is_anomaly, drop_ratio = detect_anomaly(prev_count, new_count, threshold)

    # Build info dictionary
    info = {
        'prev_count': prev_count,
        'new_count': new_count,
        'drop_ratio': drop_ratio,
        'threshold': threshold
    }

    return is_anomaly, info


def compute_final_exit_code(
    has_fatal: bool,
    has_anomaly: bool,
    no_anomaly_exit: bool = False
) -> int:
    """
    Compute final exit code based on scrape results.

    Exit codes:
    - 0: success (no fatal, no anomaly OR no_anomaly_exit is True)
    - 2: anomaly detected (has_anomaly=True and no_anomaly_exit=False)
    - 3: fatal scrape failure (has_fatal=True)

    Args:
        has_fatal: True if any URL had fatal scrape failure
        has_anomaly: True if any URL had anomaly detected
        no_anomaly_exit: If True, don't exit with code 2 for anomalies

    Returns:
        Exit code (0, 2, or 3)
    """
    # Fatal errors have highest priority
    if has_fatal:
        return 3

    # Anomaly detected and not suppressed
    if has_anomaly and not no_anomaly_exit:
        return 2

    # Success
    return 0


def format_anomaly_message(url: str, info: Dict[str, Any]) -> str:
    """
    Format anomaly warning message for logging.

    Args:
        url: Source URL
        info: Info dictionary from check_anomaly

    Returns:
        Formatted warning message
    """
    prev = info['prev_count']
    new = info['new_count']
    ratio = info['drop_ratio']
    threshold = info['threshold']

    drop_pct = ratio * 100 if ratio is not None else 0
    threshold_pct = threshold * 100

    return (f"ANOMALY: url={url} prev={prev} new={new} "
            f"drop={drop_pct:.2f}% threshold={threshold_pct:.2f}%")


def format_fatal_error_message(url: str, reason: str, strategy: Optional[str] = None) -> str:
    """
    Format fatal error message for logging.

    Args:
        url: Source URL
        reason: Error reason
        strategy: Strategy used (A, B, or None)

    Returns:
        Formatted error message
    """
    strategy_str = strategy if strategy else "none"
    return f"ERROR: url={url} scrape_failed reason={reason} strategy={strategy_str}"
