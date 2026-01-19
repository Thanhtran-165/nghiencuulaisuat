"""
Lai_suat Bridge Provider

Imports bank deposit/loan interest rates from the local `Lai_suat` project
(SQLite database) into VN Bond Lab's DuckDB.

This keeps the scraping project independent, while allowing VN Bond Lab to
use the collected history.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class LaiSuatRatesProvider:
    provider_name = "lai_suat_rates"
    provider_type = "bank_rates"
    supports_historical = True
    backfill_supported = True

    def __init__(self):
        self.lai_suat_root = Path(settings.lai_suat_root)
        self.sqlite_path = Path(settings.lai_suat_db_path)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def _get_latest_observed_day(self) -> Optional[date]:
        if not self.sqlite_path.exists():
            return None
        con = sqlite3.connect(str(self.sqlite_path))
        try:
            latest = con.execute(
                "SELECT MAX(observed_day) FROM observations WHERE observed_day IS NOT NULL"
            ).fetchone()[0]
        finally:
            con.close()
        if not latest:
            return None
        # observed_day is stored as 'YYYY-MM-DD'
        return date.fromisoformat(str(latest))

    def fetch(self, target_date: date) -> List[Dict[str, Any]]:
        """
        Fetch canonical (priority-merged) observations for a single observed day.

        If `LAI_SUAT_RUN_SCRAPER=true`, runs the Lai_suat scraper before importing.
        """
        # For daily ingestion, Lai_suat often updates the latest available observed_day,
        # which may be earlier than "today" (e.g., weekends/holidays). So we always
        # import the latest observed day after scraping.
        if getattr(settings, "lai_suat_run_scraper", False):
            self._maybe_run_scraper()
        latest_day = self._get_latest_observed_day()
        if not latest_day:
            return []
        return self._read_sqlite_range(start_date=latest_day, end_date=latest_day)

    def backfill(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """Backfill canonical observations over a date range from the SQLite history."""
        return self.read_range(start_date=start_date, end_date=end_date, run_scraper=True)

    def read_range(self, start_date: date, end_date: date, run_scraper: bool = True) -> List[Dict[str, Any]]:
        """
        Read canonical observations from SQLite over a date range.

        Use `run_scraper=False` when the caller already ran the scraper and wants to avoid
        a second run (e.g., "scrape + sync" admin button).
        """
        if run_scraper:
            self._maybe_run_scraper()
        return self._read_sqlite_range(start_date=start_date, end_date=end_date)

    def _maybe_run_scraper(self) -> None:
        self._maybe_run_scraper_force(force=False)

    def _maybe_run_scraper_force(self, force: bool = False) -> None:
        if not force and not getattr(settings, "lai_suat_run_scraper", False):
            return

        if not self.lai_suat_root.exists():
            logger.warning("Lai_suat root not found at %s; skipping scraper run.", self.lai_suat_root)
            return

        cmd = [
            sys.executable,
            "-m",
            "app.cli",
            "--db",
            str(self.sqlite_path),
            "scrape",
            "--all",
            "--no-anomaly-exit",
        ]

        logger.info("Running Lai_suat scraper to update SQLite DB...")
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.lai_suat_root),
                env={
                    **os.environ,
                    "PYTHONUNBUFFERED": "1",
                    # Ensure we import Lai_suat's own `app` package, not VN Bond Lab's.
                    "PYTHONPATH": str(self.lai_suat_root),
                },
                check=False,
                capture_output=True,
                text=True,
            )
            logger.info("Lai_suat scraper finished with exit code %s", result.returncode)
            if result.stdout:
                logger.info("Lai_suat scraper stdout (tail): %s", result.stdout[-2000:].strip())
            if result.stderr:
                logger.warning("Lai_suat scraper stderr (tail): %s", result.stderr[-2000:].strip())
        except Exception as e:
            logger.warning("Failed to run Lai_suat scraper: %s", e)

    def _read_sqlite_range(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        if not self.sqlite_path.exists():
            logger.warning("Lai_suat SQLite DB not found at %s; returning empty.", self.sqlite_path)
            return []

        con = sqlite3.connect(str(self.sqlite_path))
        con.row_factory = sqlite3.Row

        try:
            # Canonical per-day merge across sources using priority rules.
            sql = """
            WITH ranked AS (
                SELECT
                    o.observed_day AS date,
                    se.product_group AS product_group,
                    se.code AS series_code,
                    b.name AS bank_name,
                    COALESCE(t.months, -1) AS term_months,
                    t.label AS term_label,
                    o.rate_min_pct,
                    o.rate_max_pct,
                    o.rate_pct,
                    s.url AS source_url,
                    CASE
                      WHEN s.url LIKE '%timo.vn/%' THEN 1
                      ELSE COALESCE(sp.priority, 999)
                    END AS source_priority,
                    s.scraped_at AS scraped_at,
                    s.fetched_at AS fetched_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY o.observed_day, o.bank_id, o.series_id, COALESCE(o.term_id, -1)
                        ORDER BY
                          CASE
                            WHEN s.url LIKE '%timo.vn/%' THEN 1
                            ELSE COALESCE(sp.priority, 999)
                          END ASC,
                          s.scraped_at DESC,
                          o.id DESC
                    ) AS rn
                FROM observations o
                JOIN sources s ON o.source_id = s.id
                LEFT JOIN source_priorities sp ON s.url = sp.url
                JOIN banks b ON o.bank_id = b.id
                JOIN series se ON o.series_id = se.id
                LEFT JOIN terms t ON o.term_id = t.id
                WHERE o.observed_day >= ? AND o.observed_day <= ?
                  AND o.observed_day IS NOT NULL
                  AND (
                    se.code = 'deposit_online'
                    OR (
                      CASE
                        WHEN s.url LIKE '%timo.vn/%' THEN 1
                        ELSE COALESCE(sp.priority, 999)
                      END
                    ) <= ?
                  )
            )
            SELECT
                date,
                product_group,
                series_code,
                bank_name,
                term_months,
                term_label,
                rate_min_pct,
                rate_max_pct,
                rate_pct,
                source_url,
                source_priority,
                scraped_at,
                fetched_at
            FROM ranked
            WHERE rn = 1
            ORDER BY date, product_group, series_code, bank_name, term_months
            """

            rows = con.execute(
                sql,
                (
                    start_date.isoformat(),
                    end_date.isoformat(),
                    int(getattr(settings, "lai_suat_max_source_priority", 1)),
                ),
            ).fetchall()
            out: list[dict[str, Any]] = []
            for r in rows:
                out.append(
                    {
                        "date": r["date"],
                        "product_group": r["product_group"],
                        "series_code": r["series_code"],
                        "bank_name": r["bank_name"],
                        "term_months": int(r["term_months"]) if r["term_months"] is not None else -1,
                        "term_label": r["term_label"],
                        "rate_min_pct": r["rate_min_pct"],
                        "rate_max_pct": r["rate_max_pct"],
                        "rate_pct": r["rate_pct"],
                        "source_url": r["source_url"],
                        "source_priority": int(r["source_priority"]) if r["source_priority"] is not None else None,
                        "scraped_at": r["scraped_at"],
                        "fetched_at": r["fetched_at"],
                        "source": "LAI_SUAT",
                    }
                )
            return out
        finally:
            con.close()
