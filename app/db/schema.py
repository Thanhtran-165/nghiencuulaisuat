"""
DuckDB Schema initialization and management for Vietnamese Bond Data Lab
"""
import duckdb
import logging
from pathlib import Path
from typing import Optional, Any
from datetime import datetime, date, timedelta
from collections.abc import Sequence

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages DuckDB database connection and schema initialization"""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.con: Optional[duckdb.DuckDBPyConnection] = None

    def connect(self, read_only: bool = False):
        """Establish database connection"""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.con = duckdb.connect(str(self.db_path), read_only=bool(read_only))
            logger.info(f"Connected to database at {self.db_path}")
            return self.con
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def close(self):
        """Close database connection"""
        if self.con:
            self.con.close()
            logger.info("Database connection closed")

    def initialize_schema(self):
        """Initialize all database tables"""
        if not self.con:
            raise RuntimeError("Database not connected. Call connect() first.")

        logger.info("Initializing database schema...")

        # Create tables in order
        self._create_gov_yield_curve_table()
        self._create_gov_yield_change_stats_table()
        self._create_interbank_rates_table()
        self._create_ingest_runs_table()
        self._create_gov_auction_results_table()
        self._create_gov_secondary_trading_table()
        self._create_policy_rates_table()
        self._create_bank_rates_table()
        self._create_ingest_failures_table()
        self._create_transmission_daily_metrics_table()
        self._create_transmission_alerts_table()
        self._create_global_rates_daily_table()
        self._create_bondy_stress_daily_table()
        self._create_daily_snapshots_table()
        self._create_alerts_table()
        self._create_alert_thresholds_table()
        self._create_notification_channels_table()
        self._create_notification_events_table()
        self._create_report_artifacts_table()
        self._create_dq_runs_table()
        self._create_dq_results_table()
        self._create_source_fingerprints_table()

        # Data hygiene: normalize known provider scaling quirks (idempotent)
        self._normalize_abo_yield_curve_scaling()
        self._normalize_transmission_yield_scaling()

        logger.info("Database schema initialized successfully")

        # Create views
        self._create_transmission_views()
        self._create_bondy_stress_views()
        self._create_bank_rates_views()

        # Seed default alert thresholds
        self._seed_default_alert_thresholds()

    def _normalize_abo_yield_curve_scaling(self) -> None:
        """
        ABO pages often provide dot-decimal yields like "4.141" but the generic
        parser may have interpreted them as thousands (4141). Normalize those rows.
        This is safe to run repeatedly.
        """
        try:
            self.con.execute(
                """
                UPDATE gov_yield_curve
                SET
                  spot_rate_annual = spot_rate_annual / 1000.0,
                  spot_rate_continuous = CASE
                    WHEN spot_rate_continuous IS NULL THEN NULL
                    ELSE spot_rate_continuous / 1000.0
                  END,
                  par_yield = CASE
                    WHEN par_yield IS NULL THEN NULL
                    ELSE par_yield / 1000.0
                  END
                WHERE source = 'ABO'
                  AND spot_rate_annual IS NOT NULL
                  AND spot_rate_annual > 100
                  AND spot_rate_annual < 100000
                """
            )
        except Exception as e:
            logger.warning("Failed to normalize ABO yield curve scaling: %s", e)

    def _normalize_transmission_yield_scaling(self) -> None:
        """
        Earlier versions may have computed transmission yield-level metrics from
        mis-scaled yield curve inputs (e.g. 4141 instead of 4.141). Normalize
        those historical rows in-place. Safe to run repeatedly.
        """
        try:
            metric_names = (
                "level_2y",
                "level_5y",
                "level_10y",
                "slope_10y_2y",
                "slope_5y_2y",
                "curvature",
            )
            placeholders = ",".join(["?"] * len(metric_names))
            self.con.execute(
                f"""
                UPDATE transmission_daily_metrics
                SET metric_value = metric_value / 1000.0
                WHERE metric_name IN ({placeholders})
                  AND metric_value IS NOT NULL
                  AND metric_value > 100
                  AND metric_value < 100000
                """,
                list(metric_names),
            )
        except Exception as e:
            logger.warning("Failed to normalize transmission yield scaling: %s", e)

    def _create_alerts_table(self):
        """Create alerts table (rule triggers / demo seed)"""
        sql = """
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY,
            rule_code VARCHAR NOT NULL,
            severity VARCHAR NOT NULL,
            message TEXT,
            details_json TEXT,
            triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_alerts_rule_code ON alerts(rule_code);
        CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
        CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at ON alerts(triggered_at);

        CREATE SEQUENCE IF NOT EXISTS alerts_id_seq START 1;
        """

        self.con.execute(sql)
        logger.info("Created alerts table")

    def insert_alert(
        self,
        rule_code: str,
        severity: str,
        message: str,
        details: Optional[dict] = None,
        triggered_at: Optional[datetime | str] = None,
    ) -> int:
        """Insert an alert record (used by demo seed / monitoring)"""
        try:
            import json

            alert_id = self.con.execute("SELECT nextval('alerts_id_seq')").fetchone()[0]
            ts: Optional[datetime]
            if isinstance(triggered_at, str):
                ts = datetime.fromisoformat(triggered_at)
            else:
                ts = triggered_at

            sql = """
            INSERT INTO alerts (id, rule_code, severity, message, details_json, triggered_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """

            self.con.execute(
                sql,
                (
                    alert_id,
                    rule_code,
                    severity,
                    message,
                    json.dumps(details) if details is not None else None,
                    ts,
                ),
            )
            return alert_id
        except Exception as e:
            logger.error(f"Error inserting alert: {e}")
            raise

    def _normalize_records(self, records: list[Any], keys: list[str]) -> list[tuple]:
        """
        Normalize user-facing records (list[dict] or list[sequence]) into
        positional tuples suitable for DuckDB executemany with `?` placeholders.
        """
        if not records:
            return []

        first = records[0]
        if isinstance(first, dict):
            return [tuple(r.get(k) for k in keys) for r in records]
        if isinstance(first, Sequence) and not isinstance(first, (str, bytes, bytearray)):
            return [tuple(r) for r in records]

        raise TypeError("records must be a list of dicts or sequences")

    def _create_gov_yield_curve_table(self):
        """Create government bond yield curve table"""
        sql = """
        CREATE TABLE IF NOT EXISTS gov_yield_curve (
            date DATE NOT NULL,
            tenor_label VARCHAR NOT NULL,
            tenor_days INTEGER NOT NULL,
            spot_rate_continuous DOUBLE,
            par_yield DOUBLE,
            spot_rate_annual DOUBLE,
            source VARCHAR NOT NULL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, tenor_label, source)
        );

        CREATE INDEX IF NOT EXISTS idx_gov_yield_curve_date ON gov_yield_curve(date);
        CREATE INDEX IF NOT EXISTS idx_gov_yield_curve_source ON gov_yield_curve(source);
        """

        self.con.execute(sql)
        logger.info("Created gov_yield_curve table")

    def _create_gov_yield_change_stats_table(self):
        """Create government bond yield change statistics table"""
        sql = """
        CREATE TABLE IF NOT EXISTS gov_yield_change_stats (
            date DATE NOT NULL,
            bucket_label VARCHAR NOT NULL,
            currency VARCHAR,
            volume_domestic DOUBLE,
            volume_foreign DOUBLE,
            weight_domestic DOUBLE,
            weight_foreign DOUBLE,
            yield_min_domestic DOUBLE,
            yield_max_domestic DOUBLE,
            yield_min_foreign DOUBLE,
            yield_max_foreign DOUBLE,
            source VARCHAR NOT NULL,
            raw_file VARCHAR,
            UNIQUE(date, bucket_label, source)
        );

        CREATE INDEX IF NOT EXISTS idx_yield_change_stats_date ON gov_yield_change_stats(date);
        CREATE INDEX IF NOT EXISTS idx_yield_change_stats_source ON gov_yield_change_stats(source);
        """

        self.con.execute(sql)
        logger.info("Created gov_yield_change_stats table")

    def _create_interbank_rates_table(self):
        """Create interbank rates table"""
        sql = """
        CREATE TABLE IF NOT EXISTS interbank_rates (
            date DATE NOT NULL,
            tenor_label VARCHAR NOT NULL,
            rate DOUBLE NOT NULL,
            source VARCHAR NOT NULL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, tenor_label, source)
        );

        CREATE INDEX IF NOT EXISTS idx_interbank_rates_date ON interbank_rates(date);
        CREATE INDEX IF NOT EXISTS idx_interbank_rates_tenor ON interbank_rates(tenor_label);
        CREATE INDEX IF NOT EXISTS idx_interbank_rates_source ON interbank_rates(source);
        """

        self.con.execute(sql)
        logger.info("Created interbank_rates table")

    def _create_ingest_runs_table(self):
        """Create ingestion runs tracking table"""
        sql = """
        CREATE TABLE IF NOT EXISTS ingest_runs (
            id INTEGER PRIMARY KEY,
            provider VARCHAR NOT NULL,
            start_date DATE,
            end_date DATE,
            status VARCHAR NOT NULL,
            rows_inserted INTEGER DEFAULT 0,
            error_message TEXT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP
        );

        CREATE SEQUENCE IF NOT EXISTS ingest_runs_id_seq START 1;
        """

        self.con.execute(sql)
        logger.info("Created ingest_runs table")

    def _create_gov_auction_results_table(self):
        """Create government auction results table"""
        sql = """
        CREATE TABLE IF NOT EXISTS gov_auction_results (
            date DATE NOT NULL,
            instrument_type VARCHAR NOT NULL,
            tenor_label VARCHAR NOT NULL,
            tenor_days INTEGER NOT NULL,
            amount_offered DOUBLE,
            amount_sold DOUBLE,
            bid_to_cover DOUBLE,
            cut_off_yield DOUBLE,
            avg_yield DOUBLE,
            source VARCHAR NOT NULL,
            raw_file VARCHAR,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, instrument_type, tenor_label, source)
        );

        CREATE INDEX IF NOT EXISTS idx_gov_auction_results_date ON gov_auction_results(date);
        CREATE INDEX IF NOT EXISTS idx_gov_auction_results_type ON gov_auction_results(instrument_type);
        CREATE INDEX IF NOT EXISTS idx_gov_auction_results_source ON gov_auction_results(source);
        """

        self.con.execute(sql)
        logger.info("Created gov_auction_results table")

    def _create_gov_secondary_trading_table(self):
        """Create government secondary trading table"""
        sql = """
        CREATE TABLE IF NOT EXISTS gov_secondary_trading (
            date DATE NOT NULL,
            segment VARCHAR NOT NULL,
            bucket_label VARCHAR NOT NULL,
            segment_kind VARCHAR,
            segment_code VARCHAR,
            bucket_kind VARCHAR,
            bucket_code VARCHAR,
            bucket_display VARCHAR,
            volume DOUBLE,
            value DOUBLE,
            avg_yield DOUBLE,
            source VARCHAR NOT NULL,
            raw_file VARCHAR,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, segment, bucket_label, source)
        );

        CREATE INDEX IF NOT EXISTS idx_gov_secondary_trading_date ON gov_secondary_trading(date);
        CREATE INDEX IF NOT EXISTS idx_gov_secondary_trading_segment ON gov_secondary_trading(segment);
        CREATE INDEX IF NOT EXISTS idx_gov_secondary_trading_source ON gov_secondary_trading(source);
        """

        self.con.execute(sql)
        self._ensure_table_columns(
            "gov_secondary_trading",
            {
                "segment_kind": "VARCHAR",
                "segment_code": "VARCHAR",
                "bucket_kind": "VARCHAR",
                "bucket_code": "VARCHAR",
                "bucket_display": "VARCHAR",
            },
        )
        logger.info("Created gov_secondary_trading table")

    def _ensure_table_columns(self, table: str, columns: dict[str, str]) -> None:
        """
        Ensure columns exist on a table (lightweight migration).
        DuckDB doesn't support ADD COLUMN IF NOT EXISTS across all versions, so we check first.
        """
        try:
            existing = {
                row[1] for row in self.con.execute(f"PRAGMA table_info('{table}')").fetchall()
            }
            for col, col_type in columns.items():
                if col in existing:
                    continue
                self.con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        except Exception as e:
            logger.warning(f"Could not ensure columns for {table}: {e}")

    def _create_policy_rates_table(self):
        """Create policy rates table"""
        sql = """
        CREATE TABLE IF NOT EXISTS policy_rates (
            date DATE NOT NULL,
            rate_name VARCHAR NOT NULL,
            rate DOUBLE NOT NULL,
            source VARCHAR NOT NULL,
            raw_file VARCHAR,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, rate_name, source)
        );

        CREATE INDEX IF NOT EXISTS idx_policy_rates_date ON policy_rates(date);
        CREATE INDEX IF NOT EXISTS idx_policy_rates_name ON policy_rates(rate_name);
        CREATE INDEX IF NOT EXISTS idx_policy_rates_source ON policy_rates(source);
        """

        self.con.execute(sql)
        logger.info("Created policy_rates table")

    def _create_bank_rates_table(self):
        """Create bank deposit/loan rates table (imported from Lai_suat or other sources)"""
        sql = """
        CREATE TABLE IF NOT EXISTS bank_rates (
            date DATE NOT NULL,
            product_group VARCHAR NOT NULL CHECK(product_group IN ('deposit','loan')),
            series_code VARCHAR NOT NULL,
            bank_name VARCHAR NOT NULL,
            term_months INTEGER NOT NULL DEFAULT -1,
            term_label VARCHAR,
            rate_min_pct DOUBLE,
            rate_max_pct DOUBLE,
            rate_pct DOUBLE,
            source_url VARCHAR,
            source_priority INTEGER,
            scraped_at TIMESTAMP,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source VARCHAR NOT NULL,
            UNIQUE(date, series_code, bank_name, term_months)
        );

        CREATE INDEX IF NOT EXISTS idx_bank_rates_date ON bank_rates(date);
        CREATE INDEX IF NOT EXISTS idx_bank_rates_series ON bank_rates(series_code);
        CREATE INDEX IF NOT EXISTS idx_bank_rates_bank ON bank_rates(bank_name);
        CREATE INDEX IF NOT EXISTS idx_bank_rates_source ON bank_rates(source);
        """
        self.con.execute(sql)
        logger.info("Created bank_rates table")

    def _create_bank_rates_views(self):
        """Create views for latest bank rates and time series"""
        sql = """
        CREATE OR REPLACE VIEW v_bank_rates_latest AS
        SELECT *
        FROM bank_rates
        WHERE date = (SELECT MAX(date) FROM bank_rates)
        ORDER BY product_group, series_code, bank_name, term_months;
        """
        self.con.execute(sql)
        logger.info("Created bank_rates views")

    def insert_bank_rates(self, records: list[dict]) -> int:
        """Insert bank rate records with upsert"""
        try:
            if not records:
                return 0

            sql = """
            INSERT INTO bank_rates (
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
                fetched_at,
                source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (date, series_code, bank_name, term_months)
            DO UPDATE SET
                product_group = EXCLUDED.product_group,
                term_label = EXCLUDED.term_label,
                rate_min_pct = EXCLUDED.rate_min_pct,
                rate_max_pct = EXCLUDED.rate_max_pct,
                rate_pct = EXCLUDED.rate_pct,
                source_url = EXCLUDED.source_url,
                source_priority = EXCLUDED.source_priority,
                scraped_at = EXCLUDED.scraped_at,
                fetched_at = EXCLUDED.fetched_at,
                source = EXCLUDED.source
            """

            params = self._normalize_records(
                records,
                [
                    "date",
                    "product_group",
                    "series_code",
                    "bank_name",
                    "term_months",
                    "term_label",
                    "rate_min_pct",
                    "rate_max_pct",
                    "rate_pct",
                    "source_url",
                    "source_priority",
                    "scraped_at",
                    "fetched_at",
                    "source",
                ],
            )
            self.con.executemany(sql, params)
            count = len(params)
            logger.info(f"Inserted/updated {count} bank rate records")
            return count
        except Exception as e:
            logger.error(f"Error inserting bank rates: {e}")
            raise

    def get_bank_rates(
        self,
        series_code: Optional[str] = None,
        bank_name: Optional[str] = None,
        product_group: Optional[str] = None,
        term_months: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """Get bank rates with optional filters"""
        try:
            conditions = []
            params: list[Any] = []

            if series_code:
                conditions.append("series_code = ?")
                params.append(series_code)
            if bank_name:
                conditions.append("bank_name = ?")
                params.append(bank_name)
            if product_group:
                conditions.append("product_group = ?")
                params.append(product_group)
            if term_months is not None:
                conditions.append("term_months = ?")
                params.append(int(term_months))
            if start_date:
                conditions.append("date >= ?")
                params.append(start_date)
            if end_date:
                conditions.append("date <= ?")
                params.append(end_date)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            sql = f"""
            SELECT *
            FROM bank_rates
            {where_clause}
            ORDER BY date DESC, product_group, series_code, bank_name, term_months
            """

            if limit is not None:
                sql += "\nLIMIT ?"
                params.append(int(limit))

            result = self.con.execute(sql, params).fetchall()
            columns = [desc[0] for desc in self.con.description]
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Error fetching bank rates: {e}")
            raise

    def get_latest_bank_rate_averages(self, deposit_term_months: int = 12) -> dict:
        """
        Compute simple average deposit/loan rates for the latest available `bank_rates` date.

        Notes:
        - Deposit average uses `rate_pct` for the chosen term (default: 12 months).
        - Loan average uses midpoint when min+max exist; else min; else rate_pct.
        """
        deposit_date = self.con.execute(
            """
            SELECT MAX(date)
            FROM bank_rates
            WHERE product_group = 'deposit'
              AND term_months = ?
              AND rate_pct IS NOT NULL
            """,
            [int(deposit_term_months)],
        ).fetchone()[0]
        loan_date = self.con.execute(
            """
            SELECT MAX(date)
            FROM bank_rates
            WHERE product_group = 'loan'
              AND (rate_min_pct IS NOT NULL OR rate_max_pct IS NOT NULL OR rate_pct IS NOT NULL)
            """
        ).fetchone()[0]

        if deposit_date is None and loan_date is None:
            return {"latest_date": None, "deposit_avg_12m": None, "loan_avg": None}

        deposit_avg = self.con.execute(
            """
            SELECT AVG(rate_pct) AS v
            FROM bank_rates
            WHERE date = ?
              AND product_group = 'deposit'
              AND term_months = ?
              AND rate_pct IS NOT NULL
            """,
            [str(deposit_date), int(deposit_term_months)],
        ).fetchone()[0]

        loan_avg = self.con.execute(
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
            """,
            [str(loan_date)],
        ).fetchone()[0]

        return {
            "latest_date": str(max(d for d in [deposit_date, loan_date] if d is not None)),
            "deposit_avg_12m": float(deposit_avg) if deposit_avg is not None else None,
            "loan_avg": float(loan_avg) if loan_avg is not None else None,
        }

    def insert_yield_curve(self, records: list[dict]) -> int:
        """Insert yield curve records with upsert"""
        try:
            sql = """
            INSERT INTO gov_yield_curve (
                date, tenor_label, tenor_days, spot_rate_continuous,
                par_yield, spot_rate_annual, source, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (date, tenor_label, source)
            DO UPDATE SET
                tenor_days = EXCLUDED.tenor_days,
                spot_rate_continuous = EXCLUDED.spot_rate_continuous,
                par_yield = EXCLUDED.par_yield,
                spot_rate_annual = EXCLUDED.spot_rate_annual,
                fetched_at = EXCLUDED.fetched_at
            """

            params = self._normalize_records(
                records,
                [
                    "date",
                    "tenor_label",
                    "tenor_days",
                    "spot_rate_continuous",
                    "par_yield",
                    "spot_rate_annual",
                    "source",
                    "fetched_at",
                ],
            )
            self.con.executemany(sql, params)
            count = len(params)
            logger.info(f"Inserted/updated {count} yield curve records")
            return count
        except Exception as e:
            logger.error(f"Error inserting yield curve records: {e}")
            raise

    def insert_yield_change_stats(self, records: list[dict]) -> int:
        """Insert yield change statistics with upsert"""
        try:
            sql = """
            INSERT INTO gov_yield_change_stats (
                date, bucket_label, currency, volume_domestic, volume_foreign,
                weight_domestic, weight_foreign, yield_min_domestic, yield_max_domestic,
                yield_min_foreign, yield_max_foreign, source, raw_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (date, bucket_label, source)
            DO UPDATE SET
                currency = EXCLUDED.currency,
                volume_domestic = EXCLUDED.volume_domestic,
                volume_foreign = EXCLUDED.volume_foreign,
                weight_domestic = EXCLUDED.weight_domestic,
                weight_foreign = EXCLUDED.weight_foreign,
                yield_min_domestic = EXCLUDED.yield_min_domestic,
                yield_max_domestic = EXCLUDED.yield_max_domestic,
                yield_min_foreign = EXCLUDED.yield_min_foreign,
                yield_max_foreign = EXCLUDED.yield_max_foreign,
                raw_file = EXCLUDED.raw_file
            """

            params = self._normalize_records(
                records,
                [
                    "date",
                    "bucket_label",
                    "currency",
                    "volume_domestic",
                    "volume_foreign",
                    "weight_domestic",
                    "weight_foreign",
                    "yield_min_domestic",
                    "yield_max_domestic",
                    "yield_min_foreign",
                    "yield_max_foreign",
                    "source",
                    "raw_file",
                ],
            )
            self.con.executemany(sql, params)
            count = len(params)
            logger.info(f"Inserted/updated {count} yield change stats records")
            return count
        except Exception as e:
            logger.error(f"Error inserting yield change stats: {e}")
            raise

    def insert_interbank_rates(self, records: list[dict]) -> int:
        """Insert interbank rate records with upsert"""
        try:
            sql = """
            INSERT INTO interbank_rates (date, tenor_label, rate, source, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (date, tenor_label, source)
            DO UPDATE SET
                rate = EXCLUDED.rate,
                fetched_at = EXCLUDED.fetched_at
            """

            params = self._normalize_records(
                records,
                ["date", "tenor_label", "rate", "source", "fetched_at"],
            )
            self.con.executemany(sql, params)
            count = len(params)
            logger.info(f"Inserted/updated {count} interbank rate records")
            return count
        except Exception as e:
            logger.error(f"Error inserting interbank rates: {e}")
            raise

    def log_ingest_run(
        self,
        provider: str,
        start_date: Optional[str],
        end_date: Optional[str],
        status: str,
        rows_inserted: int = 0,
        error_message: Optional[str] = None
    ) -> int:
        """Log an ingestion run"""
        try:
            # DuckDB sequences can be transactional and may reuse values after rollbacks.
            # Use MAX(id)+1 to avoid duplicate PKs during long backfills.
            run_id = self.con.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM ingest_runs").fetchone()[0]

            sql = """
            INSERT INTO ingest_runs (
                id, provider, start_date, end_date, status,
                rows_inserted, error_message, started_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """

            self.con.execute(sql, (
                run_id, provider, start_date, end_date, status,
                rows_inserted, error_message, datetime.now()
            ))

            return run_id
        except Exception as e:
            logger.error(f"Error logging ingest run: {e}")
            raise

    def update_ingest_run(self, run_id: int, status: str, rows_inserted: int = 0, error_message: Optional[str] = None):
        """Update an ingestion run with completion status"""
        try:
            sql = """
            UPDATE ingest_runs
            SET status = ?, rows_inserted = ?, error_message = ?, ended_at = ?
            WHERE id = ?
            """

            self.con.execute(sql, (status, rows_inserted, error_message, datetime.now(), run_id))
        except Exception as e:
            logger.error(f"Error updating ingest run: {e}")
            raise

    def insert_ingest_run(
        self,
        started_at: datetime | str,
        status: str,
        records_processed: int,
        duration_seconds: float,
        provider: str = "demo",
    ) -> int:
        """
        Insert a synthetic ingest run record (used by monitoring/tests).
        """
        try:
            if isinstance(started_at, str):
                started_at_dt = datetime.fromisoformat(started_at)
            else:
                started_at_dt = started_at

            run_id = self.con.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM ingest_runs").fetchone()[0]
            ended_at = started_at_dt + timedelta(seconds=float(duration_seconds))

            sql = """
            INSERT INTO ingest_runs (
                id, provider, start_date, end_date, status,
                rows_inserted, error_message, started_at, ended_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            self.con.execute(
                sql,
                (
                    run_id,
                    provider,
                    None,
                    None,
                    status,
                    int(records_processed),
                    None,
                    started_at_dt,
                    ended_at,
                ),
            )
            return run_id
        except Exception as e:
            logger.error(f"Error inserting ingest run: {e}")
            raise

    def insert_dq_run(
        self,
        run_at: datetime | str,
        status: str,
        total_rules: int,
        passed_rules: int,
        failed_rules: int,
        target_date: Optional[date] = None,
        summary_json: Optional[str] = None,
    ) -> int:
        """
        Insert a data quality run record (used by monitoring/tests).
        """
        try:
            if isinstance(run_at, str):
                run_at_dt = datetime.fromisoformat(run_at)
            else:
                run_at_dt = run_at

            run_id = self.con.execute("SELECT nextval('dq_runs_id_seq')").fetchone()[0]
            target = target_date or run_at_dt.date()

            sql = """
            INSERT INTO dq_runs (
                id, run_at, target_date, status,
                total_rules, passed_rules, failed_rules, summary_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """

            self.con.execute(
                sql,
                (
                    run_id,
                    run_at_dt,
                    target,
                    status,
                    int(total_rules),
                    int(passed_rules),
                    int(failed_rules),
                    summary_json,
                ),
            )
            return run_id
        except Exception as e:
            logger.error(f"Error inserting DQ run: {e}")
            raise

    def get_latest_yield_curve(self, date: Optional[str] = None) -> list[dict]:
        """Get yield curve for a specific date or latest available"""
        try:
            if date:
                target_date_expr = "?"
                params = [date]
            else:
                # Prefer the official HNX curve date for "latest" UI views.
                target_date_expr = """
                COALESCE(
                  (SELECT MAX(date) FROM gov_yield_curve WHERE source IN ('HNX_YC','HNX')),
                  (SELECT MAX(date) FROM gov_yield_curve)
                )
                """
                params = []

            # Prefer the official HNX yield curve when available; fall back to ABO.
            sql = f"""
            WITH base AS (
              SELECT *
              FROM gov_yield_curve
              WHERE date = {target_date_expr}
            ),
            ranked AS (
              SELECT
                date,
                tenor_label,
                tenor_days,
                spot_rate_continuous,
                par_yield,
                spot_rate_annual,
                source,
                fetched_at,
                ROW_NUMBER() OVER (
                  PARTITION BY tenor_label
                  ORDER BY
                    CASE
                      WHEN source IN ('HNX_YC','HNX') THEN 1
                      WHEN source = 'ABO' THEN 2
                      ELSE 9
                    END ASC,
                    fetched_at DESC
                ) AS rn
              FROM base
            )
            SELECT
              date,
              tenor_label,
              tenor_days,
              spot_rate_continuous,
              par_yield,
              spot_rate_annual,
              source,
              fetched_at
            FROM ranked
            WHERE rn = 1
            ORDER BY tenor_days
            """
            result = self.con.execute(sql, params).fetchall()

            columns = [desc[0] for desc in self.con.description]
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Error fetching yield curve: {e}")
            raise

    def get_interbank_rates(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        tenor: Optional[str] = None
    ) -> list[dict]:
        """
        Get interbank rates with optional filters.

        Notes:
        - Canonicalizes per (date, tenor_label): SBV > ABO > others, then newest fetched_at.
        - This avoids duplicates across providers when serving timeseries to the UI.
        """
        try:
            conditions = []
            params = []

            if start_date:
                conditions.append("date >= ?")
                params.append(start_date)
            if end_date:
                conditions.append("date <= ?")
                params.append(end_date)
            if tenor:
                conditions.append("tenor_label = ?")
                params.append(tenor)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            sql = f"""
            WITH base AS (
              SELECT
                date,
                tenor_label,
                rate,
                source,
                fetched_at
              FROM interbank_rates
              {where_clause}
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
            SELECT
              date,
              tenor_label,
              rate,
              source,
              fetched_at
            FROM ranked
            WHERE rn = 1
            ORDER BY date DESC, tenor_label
            """

            result = self.con.execute(sql, params).fetchall()
            columns = [desc[0] for desc in self.con.description]
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Error fetching interbank rates: {e}")
            raise

    def insert_auction_results(self, records: list[dict]) -> int:
        """Insert auction result records with upsert"""
        try:
            sql = """
            INSERT INTO gov_auction_results (
                date, instrument_type, tenor_label, tenor_days,
                amount_offered, amount_sold, bid_to_cover, cut_off_yield,
                avg_yield, source, raw_file, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (date, instrument_type, tenor_label, source)
            DO UPDATE SET
                tenor_days = EXCLUDED.tenor_days,
                amount_offered = EXCLUDED.amount_offered,
                amount_sold = EXCLUDED.amount_sold,
                bid_to_cover = EXCLUDED.bid_to_cover,
                cut_off_yield = EXCLUDED.cut_off_yield,
                avg_yield = EXCLUDED.avg_yield,
                raw_file = EXCLUDED.raw_file,
                fetched_at = EXCLUDED.fetched_at
            """

            params = self._normalize_records(
                records,
                [
                    "date",
                    "instrument_type",
                    "tenor_label",
                    "tenor_days",
                    "amount_offered",
                    "amount_sold",
                    "bid_to_cover",
                    "cut_off_yield",
                    "avg_yield",
                    "source",
                    "raw_file",
                    "fetched_at",
                ],
            )
            self.con.executemany(sql, params)
            count = len(params)
            logger.info(f"Inserted/updated {count} auction result records")
            return count
        except Exception as e:
            logger.error(f"Error inserting auction results: {e}")
            raise

    def insert_secondary_trading(self, records: list[dict]) -> int:
        """Insert secondary trading records with upsert"""
        try:
            sql = """
            INSERT INTO gov_secondary_trading (
                date, segment, bucket_label,
                segment_kind, segment_code, bucket_kind, bucket_code, bucket_display,
                volume, value,
                avg_yield, source, raw_file, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (date, segment, bucket_label, source)
            DO UPDATE SET
                segment_kind = EXCLUDED.segment_kind,
                segment_code = EXCLUDED.segment_code,
                bucket_kind = EXCLUDED.bucket_kind,
                bucket_code = EXCLUDED.bucket_code,
                bucket_display = EXCLUDED.bucket_display,
                volume = EXCLUDED.volume,
                value = EXCLUDED.value,
                avg_yield = EXCLUDED.avg_yield,
                raw_file = EXCLUDED.raw_file,
                fetched_at = EXCLUDED.fetched_at
            """

            params = self._normalize_records(
                records,
                [
                    "date",
                    "segment",
                    "bucket_label",
                    "segment_kind",
                    "segment_code",
                    "bucket_kind",
                    "bucket_code",
                    "bucket_display",
                    "volume",
                    "value",
                    "avg_yield",
                    "source",
                    "raw_file",
                    "fetched_at",
                ],
            )
            self.con.executemany(sql, params)
            count = len(params)
            logger.info(f"Inserted/updated {count} secondary trading records")
            return count
        except Exception as e:
            logger.error(f"Error inserting secondary trading records: {e}")
            raise

    def insert_policy_rates(self, records: list[dict]) -> int:
        """Insert policy rate records with upsert"""
        try:
            sql = """
            INSERT INTO policy_rates (
                date, rate_name, rate, source, raw_file, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (date, rate_name, source)
            DO UPDATE SET
                rate = EXCLUDED.rate,
                raw_file = EXCLUDED.raw_file,
                fetched_at = EXCLUDED.fetched_at
            """

            params = self._normalize_records(
                records,
                ["date", "rate_name", "rate", "source", "raw_file", "fetched_at"],
            )
            self.con.executemany(sql, params)
            count = len(params)
            logger.info(f"Inserted/updated {count} policy rate records")
            return count
        except Exception as e:
            logger.error(f"Error inserting policy rates: {e}")
            raise

    def _create_ingest_failures_table(self):
        """Create ingestion failures tracking table"""
        sql = """
        CREATE TABLE IF NOT EXISTS ingest_failures (
            id INTEGER PRIMARY KEY,
            dataset_id VARCHAR NOT NULL,
            provider VARCHAR NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            error_type VARCHAR NOT NULL,
            error_message TEXT,
            raw_ref VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_ingest_failures_dataset ON ingest_failures(dataset_id);
        CREATE INDEX IF NOT EXISTS idx_ingest_failures_provider ON ingest_failures(provider);
        CREATE INDEX IF NOT EXISTS idx_ingest_failures_created_at ON ingest_failures(created_at);

        CREATE SEQUENCE IF NOT EXISTS ingest_failures_id_seq START 1;
        """

        self.con.execute(sql)
        logger.info("Created ingest_failures table")

    def log_ingest_failure(
        self,
        dataset_id: str,
        provider: str,
        start_date: str,
        end_date: str,
        error_type: str,
        error_message: str,
        raw_ref: Optional[str] = None
    ):
        """Log an ingestion failure"""
        try:
            run_id = self.con.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM ingest_failures").fetchone()[0]

            sql = """
            INSERT INTO ingest_failures (
                id, dataset_id, provider, start_date, end_date,
                error_type, error_message, raw_ref
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """

            self.con.execute(sql, (
                run_id, dataset_id, provider, start_date, end_date,
                error_type, error_message, raw_ref
            ))

            logger.info(f"Logged ingest failure for {dataset_id}: {error_type}")

        except Exception as e:
            logger.error(f"Error logging ingest failure: {e}")
            raise

    def get_ingest_failures(self, limit: int = 100) -> list[dict]:
        """Get recent ingestion failures"""
        try:
            sql = """
            SELECT * FROM ingest_failures
            ORDER BY created_at DESC
            LIMIT ?
            """

            result = self.con.execute(sql, [limit]).fetchall()
            columns = [desc[0] for desc in self.con.description]
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Error fetching ingest failures: {e}")
            raise

    def get_pending_resumes(self, dataset_id: Optional[str] = None) -> list[dict]:
        """Get failed chunks that can be resumed"""
        try:
            if dataset_id:
                sql = """
                SELECT DISTINCT provider, start_date, end_date, COUNT(*) as fail_count
                FROM ingest_failures
                WHERE dataset_id = ?
                GROUP BY provider, start_date, end_date
                ORDER BY start_date DESC
                """
                result = self.con.execute(sql, [dataset_id]).fetchall()
            else:
                sql = """
                SELECT DISTINCT dataset_id, provider, start_date, end_date, COUNT(*) as fail_count
                FROM ingest_failures
                GROUP BY dataset_id, provider, start_date, end_date
                ORDER BY start_date DESC
                """
                result = self.con.execute(sql).fetchall()

            columns = [desc[0] for desc in self.con.description]
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Error fetching pending resumes: {e}")
            raise

    def get_ingest_runs(self, limit: int = 100) -> list[dict]:
        """Get recent ingestion runs"""
        try:
            sql = """
            SELECT * FROM ingest_runs
            ORDER BY started_at DESC
            LIMIT ?
            """

            result = self.con.execute(sql, [limit]).fetchall()
            columns = [desc[0] for desc in self.con.description]
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Error fetching ingest runs: {e}")
            raise

    def _create_transmission_daily_metrics_table(self):
        """Create transmission daily metrics table"""
        sql = """
        CREATE TABLE IF NOT EXISTS transmission_daily_metrics (
            date DATE NOT NULL,
            metric_name VARCHAR NOT NULL,
            metric_value DOUBLE,
            metric_value_text TEXT,
            source_components TEXT,
            computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, metric_name)
        );

        CREATE INDEX IF NOT EXISTS idx_transmission_metrics_date ON transmission_daily_metrics(date);
        CREATE INDEX IF NOT EXISTS idx_transmission_metrics_name ON transmission_daily_metrics(metric_name);
        CREATE INDEX IF NOT EXISTS idx_transmission_metrics_computed_at ON transmission_daily_metrics(computed_at);
        """

        self.con.execute(sql)
        self._ensure_table_columns(
            "transmission_daily_metrics",
            {
                "metric_value_text": "TEXT",
            },
        )
        logger.info("Created transmission_daily_metrics table")

    def _create_transmission_alerts_table(self):
        """Create transmission alerts table"""
        sql = """
        CREATE TABLE IF NOT EXISTS transmission_alerts (
            id INTEGER PRIMARY KEY,
            date DATE NOT NULL,
            alert_type VARCHAR NOT NULL,
            severity VARCHAR NOT NULL,
            message TEXT,
            metric_value DOUBLE,
            threshold DOUBLE,
            source_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_transmission_alerts_date ON transmission_alerts(date);
        CREATE INDEX IF NOT EXISTS idx_transmission_alerts_type ON transmission_alerts(alert_type);
        CREATE INDEX IF NOT EXISTS idx_transmission_alerts_severity ON transmission_alerts(severity);
        CREATE INDEX IF NOT EXISTS idx_transmission_alerts_created_at ON transmission_alerts(created_at);

        CREATE SEQUENCE IF NOT EXISTS transmission_alerts_id_seq START 1;
        """

        self.con.execute(sql)
        logger.info("Created transmission_alerts table")

    def _create_transmission_views(self):
        """Create transmission analytics views"""
        sql = """
        -- Latest metrics view
        CREATE OR REPLACE VIEW v_transmission_latest AS
        SELECT
            date,
            metric_name,
            metric_value,
            metric_value_text,
            source_components,
            computed_at
        FROM transmission_daily_metrics
        WHERE date = (SELECT MAX(date) FROM transmission_daily_metrics)
        ORDER BY metric_name;

        -- Time series view
        CREATE OR REPLACE VIEW v_transmission_timeseries AS
        SELECT
            date,
            metric_name,
            metric_value,
            metric_value_text,
            computed_at
        FROM transmission_daily_metrics
        ORDER BY metric_name, date;
        """

        self.con.execute(sql)
        logger.info("Created transmission views")

    def insert_transmission_metrics(self, date: str, metrics: dict) -> int:
        """Insert transmission metrics for a specific date"""
        try:
            import json

            records = []
            for metric_name, metric_data in metrics.items():
                value_text = None
                if isinstance(metric_data, dict):
                    value = metric_data.get('value')
                    value_text = metric_data.get('value_text')
                    source_components = json.dumps(metric_data.get('sources', {}))
                elif isinstance(metric_data, str):
                    value = None
                    value_text = metric_data
                    source_components = '{}'
                else:
                    value = metric_data
                    source_components = '{}'

                if value is not None and not isinstance(value, (int, float)):
                    continue
                if value_text is not None and not isinstance(value_text, str):
                    value_text = str(value_text)

                records.append((
                    date,
                    metric_name,
                    value,
                    value_text,
                    source_components
                ))

            sql = """
            INSERT INTO transmission_daily_metrics (date, metric_name, metric_value, metric_value_text, source_components)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (date, metric_name)
            DO UPDATE SET
                metric_value = EXCLUDED.metric_value,
                metric_value_text = EXCLUDED.metric_value_text,
                source_components = EXCLUDED.source_components
            """

            self.con.executemany(sql, records)
            count = len(records)
            logger.info(f"Inserted/updated {count} transmission metrics for {date}")
            return count
        except Exception as e:
            logger.error(f"Error inserting transmission metrics: {e}")
            raise

    def insert_transmission_alerts(self, date: str, alerts: list[dict]) -> int:
        """Insert transmission alerts for a specific date"""
        try:
            import json

            if not alerts:
                return 0

            core_types = {
                "ALERT_TRANSMISSION_TIGHTENING",
                "ALERT_TRANSMISSION_JUMP",
                "ALERT_LIQUIDITY_SPIKE",
                "ALERT_CURVE_BEAR_STEEPEN",
                "ALERT_AUCTION_WEAK",
                "ALERT_TURNOVER_DROP",
                "ALERT_POLICY_CHANGE",
                "ALERT_TRANSMISSION_HIGH",
                "ALERT_STRESS_HIGH",
            }

            # Replace semantics:
            # - If this insert is for "core transmission alerts", we delete the entire core set for the day,
            #   so stale alerts that no longer trigger get removed (fixes duplicated / wrong historical alerts).
            # - Otherwise (e.g., stress/global alerts), delete only the incoming types.
            incoming_types = {a.get("alert_type") for a in alerts if a.get("alert_type")}
            replace_types = core_types if incoming_types and incoming_types.issubset(core_types) else incoming_types

            if replace_types:
                placeholders = ",".join(["?"] * len(replace_types))
                self.con.execute(
                    f"DELETE FROM transmission_alerts WHERE date = ? AND alert_type IN ({placeholders})",
                    [date, *sorted(replace_types)],
                )

            records = []
            for alert in alerts:
                alert_id = self.con.execute("SELECT nextval('transmission_alerts_id_seq')").fetchone()[0]

                records.append((
                    alert_id,
                    date,
                    alert['alert_type'],
                    alert['severity'],
                    alert['message'],
                    alert.get('metric_value'),
                    alert.get('threshold'),
                    json.dumps(alert.get('source_data', {}))
                ))

            sql = """
            INSERT INTO transmission_alerts (
                id, date, alert_type, severity, message,
                metric_value, threshold, source_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """

            self.con.executemany(sql, records)
            count = len(records)
            logger.info(f"Inserted {count} transmission alerts for {date}")
            return count
        except Exception as e:
            logger.error(f"Error inserting transmission alerts: {e}")
            raise

    def get_transmission_metrics(
        self,
        metric_name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """Get transmission metrics with optional filters"""
        try:
            conditions = []
            params = []

            if metric_name:
                conditions.append("metric_name = ?")
                params.append(metric_name)
            if start_date:
                conditions.append("date >= ?")
                params.append(start_date)
            if end_date:
                conditions.append("date <= ?")
                params.append(end_date)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            sql = f"""
            SELECT * FROM transmission_daily_metrics
            {where_clause}
            ORDER BY date DESC, metric_name
            """

            if limit is not None:
                sql += "\nLIMIT ?"
                params.append(int(limit))

            result = self.con.execute(sql, params).fetchall()
            columns = [desc[0] for desc in self.con.description]
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Error fetching transmission metrics: {e}")
            raise

    def get_transmission_alerts(
        self,
        alert_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100
    ) -> list[dict]:
        """Get transmission alerts with optional filters"""
        try:
            conditions = []
            params = []

            if alert_type:
                conditions.append("alert_type = ?")
                params.append(alert_type)
            if start_date:
                conditions.append("date >= ?")
                params.append(start_date)
            if end_date:
                conditions.append("date <= ?")
                params.append(end_date)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            sql = f"""
            SELECT * FROM transmission_alerts
            {where_clause}
            ORDER BY date DESC, created_at DESC
            LIMIT ?
            """

            params.append(limit)
            result = self.con.execute(sql, params).fetchall()
            columns = [desc[0] for desc in self.con.description]
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Error fetching transmission alerts: {e}")
            raise

    def _create_global_rates_daily_table(self):
        """Create global rates daily table"""
        sql = """
        CREATE TABLE IF NOT EXISTS global_rates_daily (
            date DATE NOT NULL,
            series_id VARCHAR NOT NULL,
            series_name VARCHAR NOT NULL,
            value DOUBLE,
            source VARCHAR NOT NULL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, series_id, source)
        );

        CREATE INDEX IF NOT EXISTS idx_global_rates_date ON global_rates_daily(date);
        CREATE INDEX IF NOT EXISTS idx_global_rates_series ON global_rates_daily(series_id);
        CREATE INDEX IF NOT EXISTS idx_global_rates_source ON global_rates_daily(source);
        """

        self.con.execute(sql)
        logger.info("Created global_rates_daily table")

    def insert_global_rates(self, records: list[dict]) -> int:
        """Insert global rate records with upsert"""
        try:
            sql = """
            INSERT INTO global_rates_daily (
                date, series_id, series_name, value, source, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (date, series_id, source)
            DO UPDATE SET
                series_name = EXCLUDED.series_name,
                value = EXCLUDED.value,
                fetched_at = EXCLUDED.fetched_at
            """

            params = self._normalize_records(
                records,
                ["date", "series_id", "series_name", "value", "source", "fetched_at"],
            )
            self.con.executemany(sql, params)
            count = len(params)
            logger.info(f"Inserted/updated {count} global rate records")
            return count
        except Exception as e:
            logger.error(f"Error inserting global rates: {e}")
            raise

    def get_global_rates(
        self,
        series_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """Get global rates with optional filters"""
        try:
            conditions = []
            params = []

            if series_id:
                conditions.append("series_id = ?")
                params.append(series_id)
            if start_date:
                conditions.append("date >= ?")
                params.append(start_date)
            if end_date:
                conditions.append("date <= ?")
                params.append(end_date)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            sql = f"""
            SELECT * FROM global_rates_daily
            {where_clause}
            ORDER BY date DESC, series_id
            """

            if limit is not None:
                sql += "\nLIMIT ?"
                params.append(int(limit))

            result = self.con.execute(sql, params).fetchall()
            columns = [desc[0] for desc in self.con.description]
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Error fetching global rates: {e}")
            raise

    def _create_bondy_stress_daily_table(self):
        """Create BondY stress daily table"""
        sql = """
        CREATE TABLE IF NOT EXISTS bondy_stress_daily (
            date DATE NOT NULL UNIQUE,
            stress_index DOUBLE,
            regime_bucket VARCHAR,
            driver_json TEXT,
            computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_bondy_stress_date ON bondy_stress_daily(date);
        CREATE INDEX IF NOT EXISTS idx_bondy_stress_bucket ON bondy_stress_daily(regime_bucket);
        """

        self.con.execute(sql)
        logger.info("Created bondy_stress_daily table")

    def insert_bondy_stress(
        self,
        date: str,
        stress_index: Optional[float],
        regime_bucket: Optional[str],
        driver_json: str
    ) -> int:
        """Insert BondY stress record"""
        try:
            sql = """
            INSERT INTO bondy_stress_daily (date, stress_index, regime_bucket, driver_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (date)
            DO UPDATE SET
                stress_index = EXCLUDED.stress_index,
                regime_bucket = EXCLUDED.regime_bucket,
                driver_json = EXCLUDED.driver_json,
                computed_at = get_current_timestamp()
            """

            self.con.execute(sql, (date, stress_index, regime_bucket, driver_json))
            logger.info(f"Inserted/updated BondY stress for {date}")
            return 1
        except Exception as e:
            logger.error(f"Error inserting BondY stress: {e}")
            raise

    def get_bondy_stress(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """Get BondY stress data"""
        try:
            conditions = []
            params = []

            if start_date:
                conditions.append("date >= ?")
                params.append(start_date)
            if end_date:
                conditions.append("date <= ?")
                params.append(end_date)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            sql = f"""
            SELECT * FROM bondy_stress_daily
            {where_clause}
            ORDER BY date DESC
            """

            if limit is not None:
                sql += "\nLIMIT ?"
                params.append(int(limit))

            result = self.con.execute(sql, params).fetchall()
            columns = [desc[0] for desc in self.con.description]
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Error fetching BondY stress: {e}")
            raise

    def _create_bondy_stress_views(self):
        """Create BondY stress analytics views"""
        sql = """
        -- Latest BondY stress view
        CREATE OR REPLACE VIEW v_bondy_stress_latest AS
        SELECT
            date,
            stress_index,
            regime_bucket,
            driver_json,
            computed_at
        FROM bondy_stress_daily
        WHERE date = (SELECT MAX(date) FROM bondy_stress_daily);

        -- BondY stress timeseries view
        CREATE OR REPLACE VIEW v_bondy_stress_timeseries AS
        SELECT
            date,
            stress_index,
            regime_bucket,
            computed_at
        FROM bondy_stress_daily
        ORDER BY date DESC;
        """

        self.con.execute(sql)
        logger.info("Created BondY stress views")

    def _create_daily_snapshots_table(self):
        """Create daily snapshots table for audit"""
        sql = """
        CREATE TABLE IF NOT EXISTS daily_snapshots (
            date DATE NOT NULL UNIQUE,
            baseline_date DATE,
            snapshot_json TEXT,
            snapshot_text TEXT,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source_components_json TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_daily_snapshots_date ON daily_snapshots(date);
        CREATE INDEX IF NOT EXISTS idx_daily_snapshots_baseline ON daily_snapshots(baseline_date);
        """

        self.con.execute(sql)
        logger.info("Created daily_snapshots table")

    def insert_daily_snapshot(
        self,
        date: str,
        baseline_date: Optional[str],
        snapshot_json: str,
        snapshot_text: Optional[str] = None,
        source_components: Optional[dict] = None
    ) -> int:
        """Insert daily snapshot"""
        try:
            import json

            sql = """
            INSERT INTO daily_snapshots (date, baseline_date, snapshot_json, snapshot_text, source_components_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (date)
            DO UPDATE SET
                baseline_date = EXCLUDED.baseline_date,
                snapshot_json = EXCLUDED.snapshot_json,
                snapshot_text = EXCLUDED.snapshot_text,
                source_components_json = EXCLUDED.source_components_json,
                generated_at = get_current_timestamp()
            """

            self.con.execute(sql, (
                date,
                baseline_date,
                snapshot_json,
                snapshot_text,
                json.dumps(source_components) if source_components else None
            ))

            logger.info(f"Inserted/updated daily snapshot for {date}")
            return 1
        except Exception as e:
            logger.error(f"Error inserting daily snapshot: {e}")
            raise

    def get_daily_snapshot(self, date: str) -> Optional[dict]:
        """Get daily snapshot for specific date"""
        try:
            sql = """
            SELECT * FROM daily_snapshots
            WHERE date = ?
            """

            result = self.con.execute(sql, [date]).fetchone()

            if result:
                columns = [desc[0] for desc in self.con.description]
                return dict(zip(columns, result))

            return None
        except Exception as e:
            logger.error(f"Error getting daily snapshot: {e}")
            raise

    def _create_alert_thresholds_table(self):
        """Create alert thresholds table"""
        sql = """
        CREATE TABLE IF NOT EXISTS alert_thresholds (
            id INTEGER PRIMARY KEY,
            alert_code VARCHAR NOT NULL UNIQUE,
            enabled BOOLEAN DEFAULT TRUE,
            severity VARCHAR NOT NULL,
            params_json TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_alert_thresholds_code ON alert_thresholds(alert_code);
        CREATE INDEX IF NOT EXISTS idx_alert_thresholds_enabled ON alert_thresholds(enabled);

        CREATE SEQUENCE IF NOT EXISTS alert_thresholds_id_seq START 1;
        """

        self.con.execute(sql)
        logger.info("Created alert_thresholds table")

    def _seed_default_alert_thresholds(self):
        """Seed default alert thresholds (insert missing only)"""

        import json

        default_thresholds = [
            {
                'alert_code': 'ALERT_TRANSMISSION_TIGHTENING',
                'enabled': True,
                'severity': 'MEDIUM',
                'params': {'lookback': 120, 'min_n': 30, 'z_low': 1.0, 'z_medium': 1.3, 'z_high': 2.0}
            },
            {
                'alert_code': 'ALERT_TRANSMISSION_JUMP',
                'enabled': True,
                'severity': 'MEDIUM',
                'params': {'jump_medium': 7.0, 'jump_high': 12.0}
            },
            {
                'alert_code': 'ALERT_LIQUIDITY_SPIKE',
                'enabled': True,
                'severity': 'HIGH',
                'params': {'z_min': 2.0, 'on_min': 2.0}
            },
            {
                'alert_code': 'ALERT_CURVE_BEAR_STEEPEN',
                'enabled': True,
                'severity': 'HIGH',
                'params': {'bps_change_20d_min': 20, 'slope_min': 2.0}  # 20 bps, 2.0%
            },
            {
                'alert_code': 'ALERT_AUCTION_WEAK',
                'enabled': True,
                'severity': 'MEDIUM',
                'params': {'btc_max': 1.2}
            },
            {
                'alert_code': 'ALERT_TURNOVER_DROP',
                'enabled': True,
                'severity': 'MEDIUM',
                'params': {'z_max': -1.5}
            },
            {
                'alert_code': 'ALERT_POLICY_CHANGE',
                'enabled': True,
                'severity': 'HIGH',
                'params': {'any_change': True}
            },
            {
                'alert_code': 'ALERT_GLOBAL_RATE_SHOCK',
                'enabled': True,
                'severity': 'HIGH',
                'params': {'us10y_bps_change_5d_min': 25}  # 25 bps
            },
            {
                'alert_code': 'ALERT_SPREAD_WIDENING',
                'enabled': True,
                'severity': 'HIGH',
                'params': {'spread_bps_change_5d_min': 50}  # 50 bps
            }
        ]

        # Load existing codes to avoid overwriting user edits.
        existing_rows = self.con.execute("SELECT alert_code, enabled, severity, params_json FROM alert_thresholds").fetchall()
        existing_codes = {r[0] for r in existing_rows} if existing_rows else set()

        # Targeted migration: fix legacy key "zscore_max" -> "z_max" for turnover alert.
        for code, enabled, severity, params_json in existing_rows or []:
            if code != "ALERT_TURNOVER_DROP" or not params_json:
                continue
            try:
                params = json.loads(params_json)
            except Exception:
                continue
            if isinstance(params, dict) and "zscore_max" in params and "z_max" not in params:
                params["z_max"] = params.pop("zscore_max")
                self.upsert_alert_threshold(alert_code=code, enabled=bool(enabled), severity=str(severity), params=params)
                logger.info("Migrated ALERT_TURNOVER_DROP params: zscore_max -> z_max")

        for threshold in default_thresholds:
            try:
                if threshold['alert_code'] in existing_codes:
                    continue

                alert_id = self.con.execute("SELECT nextval('alert_thresholds_id_seq')").fetchone()[0]

                sql = """
                INSERT INTO alert_thresholds (id, alert_code, enabled, severity, params_json)
                VALUES (?, ?, ?, ?, ?)
                """

                self.con.execute(sql, (
                    alert_id,
                    threshold['alert_code'],
                    threshold['enabled'],
                    threshold['severity'],
                    json.dumps(threshold['params'])
                ))

                logger.info(f"Seeded alert threshold: {threshold['alert_code']}")

            except Exception as e:
                logger.warning(f"Failed to seed threshold {threshold['alert_code']}: {e}")

        logger.info("Default alert thresholds ensured (missing inserted)")

    def get_alert_thresholds(self, enabled_only: bool = False) -> list[dict]:
        """Get alert thresholds"""
        try:
            conditions = []
            params = []

            if enabled_only:
                conditions.append("enabled = ?")
                params.append(True)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            sql = f"""
            SELECT * FROM alert_thresholds
            {where_clause}
            ORDER BY alert_code
            """

            result = self.con.execute(sql, params).fetchall()
            columns = [desc[0] for desc in self.con.description]
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Error getting alert thresholds: {e}")
            raise

    def upsert_alert_threshold(self, alert_code: str, enabled: bool, severity: str, params: dict) -> int:
        """Insert or update alert threshold"""
        try:
            import json

            # Check if exists
            existing = self.con.execute(
                "SELECT id FROM alert_thresholds WHERE alert_code = ?",
                [alert_code]
            ).fetchone()

            if existing:
                # Update
                sql = """
                UPDATE alert_thresholds
                SET enabled = ?, severity = ?, params_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE alert_code = ?
                """

                self.con.execute(sql, (enabled, severity, json.dumps(params), alert_code))
            else:
                # Insert
                alert_id = self.con.execute("SELECT nextval('alert_thresholds_id_seq')").fetchone()[0]

                sql = """
                INSERT INTO alert_thresholds (id, alert_code, enabled, severity, params_json)
                VALUES (?, ?, ?, ?, ?)
                """

                self.con.execute(sql, (alert_id, alert_code, enabled, severity, json.dumps(params)))

            logger.info(f"Upserted alert threshold: {alert_code}")
            return 1
        except Exception as e:
            logger.error(f"Error upserting alert threshold: {e}")
            raise

    def _create_notification_channels_table(self):
        """Create notification channels table"""
        sql = """
        CREATE TABLE IF NOT EXISTS notification_channels (
            id INTEGER PRIMARY KEY,
            channel_type VARCHAR NOT NULL,
            enabled BOOLEAN DEFAULT FALSE,
            config_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_notification_channels_type ON notification_channels(channel_type);
        CREATE INDEX IF NOT EXISTS idx_notification_channels_enabled ON notification_channels(enabled);

        CREATE SEQUENCE IF NOT EXISTS notification_channels_id_seq START 1;
        """

        self.con.execute(sql)
        logger.info("Created notification_channels table")

    def get_notification_channels(self, enabled_only: bool = True) -> list[dict]:
        """Get notification channels"""
        try:
            conditions = []
            params = []

            if enabled_only:
                conditions.append("enabled = ?")
                params.append(True)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            sql = f"""
            SELECT * FROM notification_channels
            {where_clause}
            ORDER BY id
            """

            result = self.con.execute(sql, params).fetchall()
            columns = [desc[0] for desc in self.con.description]
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Error getting notification channels: {e}")
            raise

    def upsert_notification_channel(self, channel_type: str, enabled: bool, config: dict) -> int:
        """Insert or update notification channel"""
        try:
            import json

            # Check if exists
            existing = self.con.execute(
                "SELECT id FROM notification_channels WHERE channel_type = ?",
                [channel_type]
            ).fetchone()

            if existing:
                # Update
                sql = """
                UPDATE notification_channels
                SET enabled = ?, config_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE channel_type = ?
                """

                self.con.execute(sql, (enabled, json.dumps(config), channel_type))
            else:
                # Insert
                channel_id = self.con.execute("SELECT nextval('notification_channels_id_seq')").fetchone()[0]

                sql = """
                INSERT INTO notification_channels (id, channel_type, enabled, config_json)
                VALUES (?, ?, ?, ?)
                """

                self.con.execute(sql, (channel_id, channel_type, enabled, json.dumps(config)))

            logger.info(f"Upserted notification channel: {channel_type}")
            return 1
        except Exception as e:
            logger.error(f"Error upserting notification channel: {e}")
            raise

    def _create_notification_events_table(self):
        """Create notification events table"""
        sql = """
        CREATE TABLE IF NOT EXISTS notification_events (
            id INTEGER PRIMARY KEY,
            date DATE NOT NULL,
            alert_code VARCHAR NOT NULL,
            channel_id INTEGER NOT NULL,
            status VARCHAR NOT NULL,
            error_message TEXT,
            sent_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_notification_events_date ON notification_events(date);
        CREATE INDEX IF NOT EXISTS idx_notification_events_alert ON notification_events(alert_code);
        CREATE INDEX IF NOT EXISTS idx_notification_events_status ON notification_events(status);
        CREATE INDEX IF NOT EXISTS idx_notification_events_channel ON notification_events(channel_id);

        CREATE SEQUENCE IF NOT EXISTS notification_events_id_seq START 1;
        """

        self.con.execute(sql)
        logger.info("Created notification_events table")

    def insert_notification_event(
        self,
        date: str,
        alert_code: str,
        channel_id: int,
        status: str,
        error_message: Optional[str] = None
    ) -> int:
        """Insert notification event"""
        try:
            event_id = self.con.execute("SELECT nextval('notification_events_id_seq')").fetchone()[0]

            sql = """
            INSERT INTO notification_events (id, date, alert_code, channel_id, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?)
            """

            self.con.execute(sql, (event_id, date, alert_code, channel_id, status, error_message))
            logger.info(f"Logged notification event: {alert_code} -> {status}")
            return event_id
        except Exception as e:
            logger.error(f"Error inserting notification event: {e}")
            raise

    def has_notification_been_sent(self, date: str, alert_code: str, channel_id: int) -> bool:
        """Check if notification has already been sent for this date/alert/channel"""
        try:
            sql = """
            SELECT COUNT(*) as count
            FROM notification_events
            WHERE date = ? AND alert_code = ? AND channel_id = ? AND status = 'sent'
            """

            result = self.con.execute(sql, [date, alert_code, channel_id]).fetchone()
            return result and result[0] > 0
        except Exception as e:
            logger.error(f"Error checking notification sent status: {e}")
            return False

    def _create_report_artifacts_table(self):
        """Create report artifacts table for caching"""
        sql = """
        CREATE TABLE IF NOT EXISTS report_artifacts (
            id INTEGER PRIMARY KEY,
            report_type VARCHAR NOT NULL,
            date DATE NOT NULL,
            file_path VARCHAR NOT NULL,
            file_size BIGINT,
            status VARCHAR NOT NULL,
            error_message TEXT,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(report_type, date)
        );

        CREATE INDEX IF NOT EXISTS idx_report_artifacts_type ON report_artifacts(report_type);
        CREATE INDEX IF NOT EXISTS idx_report_artifacts_date ON report_artifacts(date);
        CREATE INDEX IF NOT EXISTS idx_report_artifacts_status ON report_artifacts(status);

        CREATE SEQUENCE IF NOT EXISTS report_artifacts_id_seq START 1;
        """

        self.con.execute(sql)
        logger.info("Created report_artifacts table")

    def insert_report_artifact(
        self,
        report_type: str,
        date: str,
        file_path: str,
        file_size: int,
        status: str = 'success',
        error_message: Optional[str] = None
    ) -> int:
        """Insert report artifact record"""
        try:
            artifact_id = self.con.execute("SELECT nextval('report_artifacts_id_seq')").fetchone()[0]

            sql = """
            INSERT INTO report_artifacts (id, report_type, date, file_path, file_size, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (report_type, date)
            DO UPDATE SET
                file_path = EXCLUDED.file_path,
                file_size = EXCLUDED.file_size,
                status = EXCLUDED.status,
                error_message = EXCLUDED.error_message,
                generated_at = get_current_timestamp()
            """

            self.con.execute(sql, (artifact_id, report_type, date, file_path, file_size, status, error_message))
            logger.info(f"Inserted report artifact: {report_type} for {date}")
            return artifact_id
        except Exception as e:
            logger.error(f"Error inserting report artifact: {e}")
            raise

    def get_report_artifact(self, report_type: str, date: str) -> Optional[dict]:
        """Get report artifact for specific type and date"""
        try:
            sql = """
            SELECT * FROM report_artifacts
            WHERE report_type = ? AND date = ? AND status = 'success'
            """

            result = self.con.execute(sql, [report_type, date]).fetchone()

            if result:
                columns = [desc[0] for desc in self.con.description]
                return dict(zip(columns, result))

            return None
        except Exception as e:
            logger.error(f"Error getting report artifact: {e}")
            raise

    def _create_dq_runs_table(self):
        """Create data quality runs table"""
        sql = """
        CREATE TABLE IF NOT EXISTS dq_runs (
            id INTEGER PRIMARY KEY,
            run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            target_date DATE NOT NULL,
            status VARCHAR NOT NULL,
            total_rules INTEGER,
            passed_rules INTEGER,
            failed_rules INTEGER,
            summary_json TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_dq_runs_target_date ON dq_runs(target_date);
        CREATE INDEX IF NOT EXISTS idx_dq_runs_status ON dq_runs(status);

        CREATE SEQUENCE IF NOT EXISTS dq_runs_id_seq START 1;
        """

        self.con.execute(sql)
        logger.info("Created dq_runs table")

    def _create_dq_results_table(self):
        """Create data quality results table"""
        sql = """
        CREATE TABLE IF NOT EXISTS dq_results (
            id INTEGER PRIMARY KEY,
            target_date DATE NOT NULL,
            dataset_id VARCHAR NOT NULL,
            rule_code VARCHAR NOT NULL,
            severity VARCHAR NOT NULL,
            passed BOOLEAN NOT NULL,
            message TEXT,
            details_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(target_date, dataset_id, rule_code)
        );

        CREATE INDEX IF NOT EXISTS idx_dq_results_target_date ON dq_results(target_date);
        CREATE INDEX IF NOT EXISTS idx_dq_results_dataset ON dq_results(dataset_id);
        CREATE INDEX IF NOT EXISTS idx_dq_results_severity ON dq_results(severity);

        CREATE SEQUENCE IF NOT EXISTS dq_results_id_seq START 1;
        """

        self.con.execute(sql)
        logger.info("Created dq_results table")

    def _create_source_fingerprints_table(self):
        """Create source fingerprints table for drift detection"""
        sql = """
        CREATE TABLE IF NOT EXISTS source_fingerprints (
            id INTEGER PRIMARY KEY,
            provider VARCHAR NOT NULL,
            dataset_id VARCHAR NOT NULL,
            target_date DATE NOT NULL,
            fingerprint_hash VARCHAR NOT NULL,
            content_type VARCHAR,
            bytes INTEGER,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            parse_rowcount INTEGER,
            parse_required_fields_ok BOOLEAN,
            note TEXT,
            UNIQUE(provider, dataset_id, target_date, fingerprint_hash)
        );

        CREATE INDEX IF NOT EXISTS idx_source_fingerprints_provider ON source_fingerprints(provider);
        CREATE INDEX IF NOT EXISTS idx_source_fingerprints_dataset ON source_fingerprints(dataset_id);
        CREATE INDEX IF NOT EXISTS idx_source_fingerprints_date ON source_fingerprints(target_date);
        CREATE INDEX IF NOT EXISTS idx_source_fingerprints_hash ON source_fingerprints(fingerprint_hash);

        CREATE SEQUENCE IF NOT EXISTS source_fingerprints_id_seq START 1;
        """

        self.con.execute(sql)
        logger.info("Created source_fingerprints table")

    def insert_source_fingerprint(
        self,
        provider: str,
        dataset_id: str,
        target_date: str | date,
        content: bytes,
        content_type: str,
        parse_rowcount: int,
        parse_required_fields_ok: bool,
        note: Optional[str] = None
    ) -> str:
        """
        Insert a source fingerprint record

        Returns:
            fingerprint_hash (SHA256)
        """
        import hashlib

        # Compute fingerprint hash
        fingerprint_hash = hashlib.sha256(content).hexdigest()

        try:
            fingerprint_id = self.con.execute("SELECT nextval('source_fingerprints_id_seq')").fetchone()[0]
            sql = """
            INSERT INTO source_fingerprints (
                id, provider, dataset_id, target_date, fingerprint_hash,
                content_type, bytes, parse_rowcount, parse_required_fields_ok, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (provider, dataset_id, target_date, fingerprint_hash)
            DO NOTHING
            """

            self.con.execute(sql, [
                fingerprint_id,
                provider,
                dataset_id,
                target_date,
                fingerprint_hash,
                content_type,
                len(content),
                parse_rowcount,
                parse_required_fields_ok,
                note
            ])

            logger.info(f"Inserted fingerprint for {provider}/{dataset_id} on {target_date}: {fingerprint_hash[:16]}...")
            return fingerprint_hash

        except Exception as e:
            logger.error(f"Error inserting source fingerprint: {e}")
            raise

    def get_source_fingerprints(
        self,
        provider: Optional[str] = None,
        dataset_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100
    ) -> list:
        """Get source fingerprints with filters"""
        try:
            sql = """
            SELECT * FROM source_fingerprints
            WHERE 1=1
            """

            params = []

            if provider:
                sql += " AND provider = ?"
                params.append(provider)

            if dataset_id:
                sql += " AND dataset_id = ?"
                params.append(dataset_id)

            if start_date:
                sql += " AND target_date >= ?"
                params.append(start_date)

            if end_date:
                sql += " AND target_date <= ?"
                params.append(end_date)

            sql += " ORDER BY fetched_at DESC LIMIT ?"
            params.append(limit)

            results = self.con.execute(sql, params).fetchall()

            fingerprints = []
            for row in results:
                columns = [desc[0] for desc in self.con.description]
                fingerprints.append(dict(zip(columns, row)))

            return fingerprints

        except Exception as e:
            logger.error(f"Error getting source fingerprints: {e}")
            return []

    def check_fingerprint_drift(
        self,
        provider: str,
        dataset_id: str,
        target_date: str,
        current_fingerprint: str
    ) -> Optional[dict]:
        """
        Check for fingerprint drift compared to previous fetches

        Returns:
            Drift info dict if drift detected, None otherwise
        """
        try:
            # Get previous fingerprints for this provider/dataset
            sql = """
            SELECT fingerprint_hash, parse_rowcount, parse_required_fields_ok,
                   target_date, fetched_at
            FROM source_fingerprints
            WHERE provider = ? AND dataset_id = ?
            ORDER BY fetched_at DESC
            LIMIT 5
            """

            results = self.con.execute(sql, [provider, dataset_id]).fetchall()

            if not results:
                # No previous fingerprints - this is first fetch
                return None

            # Check if fingerprint changed
            previous_fp = results[0][0]

            if previous_fp != current_fingerprint:
                # Fingerprint changed - check for regression
                current_rowcount = self.con.execute(
                    "SELECT parse_rowcount FROM source_fingerprints WHERE fingerprint_hash = ?",
                    [current_fingerprint]
                ).fetchone()

                previous_rowcount = results[0][1]

                drift_info = {
                    'previous_fingerprint': previous_fp[:16] + '...',
                    'current_fingerprint': current_fingerprint[:16] + '...',
                    'previous_rowcount': previous_rowcount,
                    'current_rowcount': current_rowcount[0] if current_rowcount else None,
                    'drift_type': 'content_changed'
                }

                # Check for regression (rowcount drop)
                if current_rowcount and previous_rowcount:
                    rowcount_change = current_rowcount[0] - previous_rowcount
                    if rowcount_change < -0.1 * previous_rowcount:  # More than 10% drop
                        drift_info['regression'] = True
                        drift_info['regression_reason'] = f"Rowcount dropped by {abs(rowcount_change)} rows"

                return drift_info

            return None

        except Exception as e:
            logger.error(f"Error checking fingerprint drift: {e}")
            return None


# Lightweight, test-friendly singleton.
# The main app wires its own DatabaseManager instance via app.main/routes.
db_manager = DatabaseManager(":memory:")
