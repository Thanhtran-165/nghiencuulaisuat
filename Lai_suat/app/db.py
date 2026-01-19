"""Database layer for bank interest rate scraper."""

import sqlite3
import os
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from .utils import logger


class Database:
    """Database connection and schema management."""

    def __init__(self, db_path: str):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    @contextmanager
    def get_connection(self):
        """
        Context manager for database connection.

        Yields:
            sqlite3.Connection: Database connection
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        """Initialize database schema with all required tables."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Create sources table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    scraped_at TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    page_updated_text TEXT,
                    UNIQUE(url, content_hash)
                )
            ''')

            # Create banks table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS banks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                )
            ''')

            # Create terms table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS terms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label TEXT NOT NULL UNIQUE,
                    months INTEGER NOT NULL
                )
            ''')

            # Create series table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS series (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_group TEXT NOT NULL CHECK(product_group IN ('deposit', 'loan')),
                    code TEXT NOT NULL UNIQUE,
                    description TEXT
                )
            ''')

            # Create observations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER NOT NULL,
                    bank_id INTEGER NOT NULL,
                    series_id INTEGER NOT NULL,
                    term_id INTEGER,
                    rate_min_pct REAL,
                    rate_max_pct REAL,
                    rate_pct REAL,
                    FOREIGN KEY (source_id) REFERENCES sources(id),
                    FOREIGN KEY (bank_id) REFERENCES banks(id),
                    FOREIGN KEY (series_id) REFERENCES series(id),
                    FOREIGN KEY (term_id) REFERENCES terms(id),
                    UNIQUE(source_id, bank_id, series_id, term_id)
                )
            ''')

            # Create source_priorities table for multi-source merge
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS source_priorities (
                    url TEXT PRIMARY KEY,
                    priority INTEGER NOT NULL DEFAULT 999,
                    notes TEXT
                )
            ''')

            # Create indexes for better query performance
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_sources_url ON sources(url)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_observations_source_id
                ON observations(source_id)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_observations_bank_id
                ON observations(bank_id)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_observations_series_id
                ON observations(series_id)
            ''')

            logger.info(f"Database schema initialized at {self.db_path}")

            # Ensure schema has all required columns (migration)
            self.ensure_schema()

            # Create views for latest data
            self.create_views()

            # Seed series codes
            self.seed_series()

            # Seed source priorities
            self.seed_source_priorities()

    def ensure_schema(self) -> None:
        """
        Ensure database schema has all required columns for backward compatibility.

        Adds new columns if they don't exist (non-destructive migration).
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check and add columns to sources table
            cursor.execute("PRAGMA table_info(sources)")
            sources_columns = {row['name'] for row in cursor.fetchall()}

            sources_new_columns = {
                # Raw (unsalted) content hash to detect real page changes over time.
                # `content_hash` may be salted by observed_day to allow daily snapshots.
                'content_hash_raw': 'TEXT',
                'strategy_used': 'TEXT',
                'parse_version': 'TEXT',
                'http_status': 'INTEGER',
                'fetched_at': 'TEXT',
                'record_count_extracted': 'INTEGER',
                'record_count_inserted': 'INTEGER',
                'dropped_duplicate_count': 'INTEGER DEFAULT 0',
                'dropped_invalid_count': 'INTEGER DEFAULT 0',
                'dropped_reason_json': 'TEXT'
            }

            for col_name, col_type in sources_new_columns.items():
                if col_name not in sources_columns:
                    cursor.execute(f'''
                        ALTER TABLE sources ADD COLUMN {col_name} {col_type}
                    ''')
                    logger.info(f"Added column {col_name} to sources table")

            # Check and add columns to observations table
            cursor.execute("PRAGMA table_info(observations)")
            observations_columns = {row['name'] for row in cursor.fetchall()}

            observations_new_columns = {
                'raw_value': 'TEXT',
                'parse_warnings': 'TEXT',
                # Daily tracking (used by canonical history and external consumers).
                'observed_day': 'TEXT'
            }

            for col_name, col_type in observations_new_columns.items():
                if col_name not in observations_columns:
                    cursor.execute(f'''
                        ALTER TABLE observations ADD COLUMN {col_name} {col_type}
                    ''')
                    logger.info(f"Added column {col_name} to observations table")

            # (Re)compute observed_day based on Vietnam local date (UTC+7) using source.scraped_at.
            # This is safe to run repeatedly and avoids confusing "day mismatch" in the UI.
            if 'observed_day' in observations_columns or 'observed_day' in observations_new_columns:
                try:
                    cursor.execute('''
                        UPDATE observations
                        SET observed_day = date(
                          (SELECT scraped_at FROM sources WHERE id = observations.source_id),
                          '+7 hours'
                        )
                        WHERE EXISTS (
                          SELECT 1 FROM sources
                          WHERE id = observations.source_id AND scraped_at IS NOT NULL
                        )
                    ''')
                except Exception as e:
                    logger.warning(f"Failed to compute observed_day: {e}")

            logger.info("Schema migration completed")

    def check_source_exists(self, url: str, content_hash: str) -> Optional[int]:
        """
        Check if source with given URL and content hash already exists.

        Args:
            url: Source URL
            content_hash: Content hash of the page

        Returns:
            Source ID if exists, None otherwise
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id FROM sources
                WHERE url = ? AND content_hash = ?
            ''', (url, content_hash))
            result = cursor.fetchone()
            return result[0] if result else None

    def insert_source(self, url: str, scraped_at: str,
                     content_hash: str, page_updated_text: Optional[str] = None,
                     content_hash_raw: Optional[str] = None,
                     strategy_used: Optional[str] = None,
                     parse_version: Optional[str] = None,
                     http_status: Optional[int] = None,
                     fetched_at: Optional[str] = None,
                     record_count_extracted: Optional[int] = None,
                     record_count_inserted: Optional[int] = None,
                     dropped_duplicate_count: Optional[int] = None,
                     dropped_invalid_count: Optional[int] = None,
                     dropped_reason_json: Optional[str] = None) -> int:
        """
        Insert a new source record with metadata.

        Args:
            url: Source URL
            scraped_at: ISO8601 UTC timestamp
            content_hash: SHA256 hash of content
            page_updated_text: Extracted update text from page
            content_hash_raw: Unsalted SHA256 of raw HTML (for change detection)
            strategy_used: Parsing strategy used (A or B)
            parse_version: Parser version identifier
            http_status: HTTP status code
            fetched_at: Timestamp when fetch completed
            record_count_extracted: Number of records extracted
            record_count_inserted: Number of records inserted
            dropped_duplicate_count: Number of duplicates dropped
            dropped_invalid_count: Number of invalid records dropped
            dropped_reason_json: JSON string with drop reasons

        Returns:
            ID of inserted source
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sources (
                    url, scraped_at, content_hash, page_updated_text, content_hash_raw,
                    strategy_used, parse_version, http_status, fetched_at,
                    record_count_extracted, record_count_inserted,
                    dropped_duplicate_count, dropped_invalid_count, dropped_reason_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (url, scraped_at, content_hash, page_updated_text, content_hash_raw,
                  strategy_used, parse_version, http_status, fetched_at,
                  record_count_extracted, record_count_inserted,
                  dropped_duplicate_count, dropped_invalid_count, dropped_reason_json))
            return cursor.lastrowid

    def update_source_record_count_inserted(self, source_id: int, record_count_inserted: int) -> None:
        """Update inserted record count for an existing source row."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE sources SET record_count_inserted = ? WHERE id = ?",
                (int(record_count_inserted), int(source_id)),
            )

    def upsert_bank(self, name: str) -> int:
        """
        Insert or get existing bank by name.

        Args:
            name: Bank name

        Returns:
            Bank ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO banks (name)
                VALUES (?)
            ''', (name,))
            cursor.execute('SELECT id FROM banks WHERE name = ?', (name,))
            result = cursor.fetchone()
            return result[0]

    def upsert_term(self, label: str, months: int) -> int:
        """
        Insert or get existing term by label.

        Args:
            label: Term label (e.g., "6 tháng")
            months: Term in months

        Returns:
            Term ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO terms (label, months)
                VALUES (?, ?)
            ''', (label, months))
            cursor.execute('SELECT id FROM terms WHERE label = ?', (label,))
            result = cursor.fetchone()
            return result[0]

    def upsert_series(self, product_group: str, code: str,
                     description: Optional[str] = None) -> int:
        """
        Insert or get existing series by code.

        Args:
            product_group: Either 'deposit' or 'loan'
            code: Series code (e.g., 'deposit_tai_quay')
            description: Optional description

        Returns:
            Series ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO series (product_group, code, description)
                VALUES (?, ?, ?)
            ''', (product_group, code, description))
            cursor.execute('SELECT id FROM series WHERE code = ?', (code,))
            result = cursor.fetchone()
            return result[0]

    def insert_observation(self, source_id: int, bank_id: int, series_id: int,
                          term_id: Optional[int],
                          rate_min_pct: Optional[float],
                          rate_max_pct: Optional[float],
                          rate_pct: Optional[float],
                          observed_day: Optional[str] = None,
                          raw_value: Optional[str] = None,
                          parse_warnings: Optional[str] = None) -> Optional[int]:
        """
        Insert an observation record.

        Args:
            source_id: Source ID
            bank_id: Bank ID
            series_id: Series ID
            term_id: Term ID (NULL for loan)
            rate_min_pct: Minimum rate percentage
            rate_max_pct: Maximum rate percentage
            rate_pct: Single rate percentage
            raw_value: Raw value string from source
            parse_warnings: JSON string with parse warnings

        Returns:
            Observation ID if inserted, None if duplicate
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO observations
                    (source_id, bank_id, series_id, term_id,
                     rate_min_pct, rate_max_pct, rate_pct, observed_day, raw_value, parse_warnings)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (source_id, bank_id, series_id, term_id,
                     rate_min_pct, rate_max_pct, rate_pct, observed_day, raw_value, parse_warnings))
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                # Duplicate observation (UNIQUE constraint violated)
                return None

    def get_latest_source_id(self, url: Optional[str] = None) -> Optional[int]:
        """
        Get the latest source ID.

        Args:
            url: Optional URL to filter by

        Returns:
            Latest source ID or None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if url:
                cursor.execute('''
                    SELECT id FROM sources
                    WHERE url = ?
                    ORDER BY id DESC
                    LIMIT 1
                ''', (url,))
            else:
                cursor.execute('''
                    SELECT id FROM sources
                    ORDER BY id DESC
                    LIMIT 1
                ''')
            result = cursor.fetchone()
            return result[0] if result else None

    def get_source(self, source_id: int) -> Optional[Dict[str, Any]]:
        """
        Get source details by ID.

        Args:
            source_id: Source ID

        Returns:
            Dictionary with source details or None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM sources WHERE id = ?', (source_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def get_observations_by_source(self, source_id: int) -> List[Dict[str, Any]]:
        """
        Get all observations for a source.

        Args:
            source_id: Source ID

        Returns:
            List of observation dictionaries
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT
                    o.id,
                    s.url AS source_url,
                    s.scraped_at,
                    b.name AS bank_name,
                    ser.product_group,
                    ser.code AS series_code,
                    t.label AS term_label,
                    t.months AS term_months,
                    o.rate_min_pct,
                    o.rate_max_pct,
                    o.rate_pct,
                    o.raw_value,
                    o.parse_warnings
                FROM observations o
                JOIN sources s ON o.source_id = s.id
                JOIN banks b ON o.bank_id = b.id
                JOIN series ser ON o.series_id = ser.id
                LEFT JOIN terms t ON o.term_id = t.id
                WHERE o.source_id = ?
                ORDER BY b.name, ser.code, t.months
            ''', (source_id,))
            results = cursor.fetchall()
            return [dict(row) for row in results]

    def get_all_banks(self) -> List[str]:
        """
        Get all bank names.

        Returns:
            List of bank names
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT name FROM banks ORDER BY name')
            results = cursor.fetchall()
            return [row[0] for row in results]

    def get_all_series(self) -> List[Dict[str, Any]]:
        """
        Get all series.

        Returns:
            List of series dictionaries
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM series ORDER BY code')
            results = cursor.fetchall()
            return [dict(row) for row in results]

    def create_views(self) -> None:
        """
        Create views for latest data queries.

        Creates:
        - v_latest_source_per_url: Latest source ID for each URL
        - v_latest_observations: Latest observations for each URL (per-source, not merged)
        - v_latest_observations_merged: Merged latest observations across sources (by priority)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Drop views if exist (for re-creation)
            cursor.execute('DROP VIEW IF EXISTS v_latest_source_per_url')
            cursor.execute('DROP VIEW IF EXISTS v_latest_observations')
            cursor.execute('DROP VIEW IF EXISTS v_latest_observations_merged')

            # Create view for latest source per URL
            cursor.execute('''
                CREATE VIEW v_latest_source_per_url AS
                SELECT
                    url,
                    MAX(id) AS latest_source_id,
                    MAX(scraped_at) AS latest_scraped_at
                FROM sources
                GROUP BY url
            ''')

            # Create view for latest observations (per-source, NO MERGE)
            cursor.execute('''
                CREATE VIEW v_latest_observations AS
                SELECT
                    o.id,
                    s.url AS source_url,
                    s.scraped_at,
                    b.name AS bank_name,
                    ser.product_group,
                    ser.code AS series_code,
                    t.label AS term_label,
                    t.months AS term_months,
                    o.rate_min_pct,
                    o.rate_max_pct,
                    o.rate_pct,
                    o.raw_value,
                    o.parse_warnings
                FROM observations o
                JOIN sources s ON o.source_id = s.id
                JOIN v_latest_source_per_url v ON s.url = v.url AND s.id = v.latest_source_id
                JOIN banks b ON o.bank_id = b.id
                JOIN series ser ON o.series_id = ser.id
                LEFT JOIN terms t ON o.term_id = t.id
                ORDER BY b.name, ser.code, t.months
            ''')

            # Create view for merged latest observations (by priority)
            # Logic: For each (bank_id, series_id, term_id), select ONE record:
            #   1. Lowest priority (1 = highest priority)
            #   2. If tie, most recent scraped_at
            #   3. If still tie, largest observation_id
            cursor.execute('''
                CREATE VIEW v_latest_observations_merged AS
                SELECT
                    ranked_obs.id,
                    ranked_obs.source_url,
                    ranked_obs.scraped_at,
                    ranked_obs.bank_name,
                    ranked_obs.product_group,
                    ranked_obs.series_code,
                    ranked_obs.term_label,
                    ranked_obs.term_months,
                    ranked_obs.rate_min_pct,
                    ranked_obs.rate_max_pct,
                    ranked_obs.rate_pct,
                    ranked_obs.raw_value,
                    ranked_obs.parse_warnings,
                    ranked_obs.priority AS source_priority
                FROM (
                    SELECT
                        o.id,
                        s.url AS source_url,
                        s.scraped_at,
                        b.name AS bank_name,
                        ser.product_group,
                        ser.code AS series_code,
                        t.label AS term_label,
                        t.months AS term_months,
                        o.rate_min_pct,
                        o.rate_max_pct,
                        o.rate_pct,
                        o.raw_value,
                        o.parse_warnings,
                        COALESCE(sp.priority, 999) AS priority,
                        ROW_NUMBER() OVER (
                            PARTITION BY o.bank_id, o.series_id, o.term_id
                            ORDER BY
                                COALESCE(sp.priority, 999) ASC,
                                s.scraped_at DESC,
                                o.id DESC
                        ) AS rn
                    FROM observations o
                    JOIN sources s ON o.source_id = s.id
                    JOIN v_latest_source_per_url v ON s.url = v.url AND s.id = v.latest_source_id
                    JOIN banks b ON o.bank_id = b.id
                    JOIN series ser ON o.series_id = ser.id
                    LEFT JOIN terms t ON o.term_id = t.id
                    LEFT JOIN source_priorities sp ON s.url = sp.url
                ) ranked_obs
                WHERE ranked_obs.rn = 1
                ORDER BY bank_name, series_code, term_months
            ''')

            logger.info("Views created successfully (including merged view)")

    def get_latest_observations_from_view(self, url: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get latest observations using v_latest_observations view (per-source, not merged).

        Args:
            url: Optional URL to filter by

        Returns:
            List of observation dictionaries
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if url:
                cursor.execute('''
                    SELECT * FROM v_latest_observations
                    WHERE source_url = ?
                ''', (url,))
            else:
                cursor.execute('SELECT * FROM v_latest_observations')
            results = cursor.fetchall()
            return [dict(row) for row in results]

    def get_latest_observations_merged(self, url: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get latest merged observations using v_latest_observations_merged view.

        This is the CANONICAL view that returns one record per (bank, series, term)
        by selecting the highest priority source (lowest priority number).

        Args:
            url: Optional URL to filter by

        Returns:
            List of observation dictionaries
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if url:
                cursor.execute('''
                    SELECT * FROM v_latest_observations_merged
                    WHERE source_url = ?
                ''', (url,))
            else:
                cursor.execute('SELECT * FROM v_latest_observations_merged')
            results = cursor.fetchall()
            return [dict(row) for row in results]

    def seed_source_priorities(self) -> None:
        """
        Seed initial source priorities (idempotent).

        Only inserts rows that don't exist yet. Does NOT override
        manually updated priorities. Safe to run multiple times.

        Default priorities:
        - timo sources: priority=1 (highest)
        - 24hmoney sources: priority=2
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            priorities = [
                ('https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/', 1, 'Original deposit source - highest priority'),
                ('https://timo.vn/blogs/lai-suat-vay-tin-chap-ngan-hang-nao-cao-nhat/', 1, 'Original loan source - highest priority'),
                ('https://24hmoney.vn/lai-suat-gui-ngan-hang', 2, 'Secondary deposit source'),
            ]

            for url, priority, notes in priorities:
                # INSERT OR IGNORE: only insert if url doesn't exist yet
                # Does NOT override existing priorities (safe for manual updates)
                cursor.execute('''
                    INSERT OR IGNORE INTO source_priorities (url, priority, notes)
                    VALUES (?, ?, ?)
                ''', (url, priority, notes))

            logger.info("Source priorities seeded successfully (idempotent)")

    def seed_series(self) -> None:
        """
        Seed initial series codes (idempotent).

        Only inserts rows that don't exist yet. Safe to run multiple times.

        Required series for frontend API compatibility:
        - deposit_online: Online deposit rates
        - deposit_tai_quay: Counter deposit rates
        - loan_the_chap: Secured loan rates
        - loan_tin_chap: Unsecured loan rates
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            series = [
                ('deposit', 'deposit_online', 'Tiền gửi Online'),
                ('deposit', 'deposit_tai_quay', 'Tiền gửi Tại quầy'),
                ('loan', 'loan_the_chap', 'Vay Thế chấp'),
                ('loan', 'loan_tin_chap', 'Vay Tín chấp'),
            ]

            for product_group, code, description in series:
                # INSERT OR IGNORE: only insert if code doesn't exist yet
                cursor.execute('''
                    INSERT OR IGNORE INTO series (product_group, code, description)
                    VALUES (?, ?, ?)
                ''', (product_group, code, description))

            logger.info("Series seeded successfully (idempotent)")

    def get_source_priority(self, url: str) -> int:
        """
        Get priority for a source URL.

        Args:
            url: Source URL

        Returns:
            Priority integer (lower = higher priority), defaults to 999
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT priority FROM source_priorities WHERE url = ?', (url,))
            result = cursor.fetchone()
            return result['priority'] if result else 999

    def update_source_priority(self, url: str, priority: int, notes: Optional[str] = None) -> None:
        """
        Update priority for a source URL.

        Args:
            url: Source URL
            priority: Priority integer (lower = higher priority)
            notes: Optional notes
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO source_priorities (url, priority, notes)
                VALUES (?, ?, ?)
            ''', (url, priority, notes))
            logger.info(f"Updated priority for {url}: {priority}")
