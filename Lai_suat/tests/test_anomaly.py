"""Tests for anomaly detection functionality."""

import pytest
import sqlite3
import tempfile
import os
from app.monitoring import (
    get_latest_extracted_count,
    detect_anomaly,
    check_anomaly,
    compute_final_exit_code,
    format_anomaly_message,
    format_fatal_error_message
)
from app.db import Database


class TestDetectAnomaly:
    """Unit tests for detect_anomaly function."""

    def test_anomaly_detected_above_threshold(self):
        """Test anomaly detection when drop ratio exceeds threshold."""
        prev = 100
        new = 69
        threshold = 0.30
        # drop = (100 - 69) / 100 = 31% > 30%

        is_anomaly, drop_ratio = detect_anomaly(prev, new, threshold)

        assert is_anomaly is True
        assert drop_ratio == 0.31

    def test_no_anomaly_at_threshold(self):
        """Test no anomaly when drop ratio equals threshold."""
        prev = 100
        new = 70
        threshold = 0.30
        # drop = (100 - 70) / 100 = 30% == 30%

        is_anomaly, drop_ratio = detect_anomaly(prev, new, threshold)

        assert is_anomaly is False
        assert drop_ratio == 0.30

    def test_no_anomaly_below_threshold(self):
        """Test no anomaly when drop ratio below threshold."""
        prev = 100
        new = 80
        threshold = 0.30
        # drop = (100 - 80) / 100 = 20% < 30%

        is_anomaly, drop_ratio = detect_anomaly(prev, new, threshold)

        assert is_anomaly is False
        assert drop_ratio == 0.20

    def test_no_anomaly_when_prev_count_none(self):
        """Test no anomaly when previous count is None."""
        prev = None
        new = 50
        threshold = 0.30

        is_anomaly, drop_ratio = detect_anomaly(prev, new, threshold)

        assert is_anomaly is False
        assert drop_ratio is None

    def test_no_anomaly_when_prev_count_zero(self):
        """Test no anomaly when previous count is zero."""
        prev = 0
        new = 10
        threshold = 0.30

        is_anomaly, drop_ratio = detect_anomaly(prev, new, threshold)

        assert is_anomaly is False
        assert drop_ratio is None

    def test_increase_in_records(self):
        """Test no anomaly when records increase."""
        prev = 100
        new = 150
        threshold = 0.30
        # drop = (100 - 150) / 100 = -50% (increase)

        is_anomaly, drop_ratio = detect_anomaly(prev, new, threshold)

        assert is_anomaly is False
        assert drop_ratio == -0.5

    def test_custom_threshold(self):
        """Test anomaly detection with custom threshold."""
        prev = 100
        new = 40
        threshold = 0.50
        # drop = (100 - 40) / 100 = 60% > 50%

        is_anomaly, drop_ratio = detect_anomaly(prev, new, threshold)

        assert is_anomaly is True
        assert drop_ratio == 0.60


class TestGetLatestExtractedCount:
    """Integration tests for get_latest_extracted_count."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)

        # Initialize database
        db = Database(path)
        db.init_schema()

        yield db

        # Cleanup
        os.unlink(path)

    def test_returns_latest_count_for_single_source(self, temp_db):
        """Test returns count when there's one source."""
        url = "https://example.com/test"

        with temp_db.get_connection() as conn:
            # Insert a source
            conn.execute('''
                INSERT INTO sources (url, scraped_at, content_hash, record_count_extracted)
                VALUES (?, '2026-01-04T00:00:00Z', 'hash123', 100)
            ''', (url,))

            # Get latest count
            count = get_latest_extracted_count(conn, url)

            assert count == 100

    def test_returns_latest_count_for_multiple_sources(self, temp_db):
        """Test returns latest count when there are multiple sources."""
        url = "https://example.com/test"

        with temp_db.get_connection() as conn:
            # Insert first source
            conn.execute('''
                INSERT INTO sources (url, scraped_at, content_hash, record_count_extracted)
                VALUES (?, '2026-01-03T00:00:00Z', 'hash1', 50)
            ''', (url,))

            # Insert second source
            conn.execute('''
                INSERT INTO sources (url, scraped_at, content_hash, record_count_extracted)
                VALUES (?, '2026-01-04T00:00:00Z', 'hash2', 100)
            ''', (url,))

            # Insert third source (latest by ID - inserted last)
            conn.execute('''
                INSERT INTO sources (url, scraped_at, content_hash, record_count_extracted)
                VALUES (?, '2026-01-02T00:00:00Z', 'hash3', 75)
            ''', (url,))

            # Get latest count (orders by id DESC, so returns last inserted)
            count = get_latest_extracted_count(conn, url)

            assert count == 75  # Last inserted (highest ID)

    def test_returns_none_when_no_sources(self, temp_db):
        """Test returns None when there are no sources for the URL."""
        url = "https://example.com/test"

        with temp_db.get_connection() as conn:
            count = get_latest_extracted_count(conn, url)

            assert count is None

    def test_returns_none_for_different_url(self, temp_db):
        """Test returns None when querying for a different URL."""
        url1 = "https://example.com/test1"
        url2 = "https://example.com/test2"

        with temp_db.get_connection() as conn:
            # Insert source for url1
            conn.execute('''
                INSERT INTO sources (url, scraped_at, content_hash, record_count_extracted)
                VALUES (?, '2026-01-04T00:00:00Z', 'hash123', 100)
            ''', (url1,))

            # Query for url2
            count = get_latest_extracted_count(conn, url2)

            assert count is None

    def test_handles_null_count(self, temp_db):
        """Test handles sources with NULL record_count_extracted."""
        url = "https://example.com/test"

        with temp_db.get_connection() as conn:
            # Insert source with NULL count
            conn.execute('''
                INSERT INTO sources (url, scraped_at, content_hash, record_count_extracted)
                VALUES (?, '2026-01-04T00:00:00Z', 'hash123', NULL)
            ''', (url,))

            # Get latest count
            count = get_latest_extracted_count(conn, url)

            assert count is None


class TestCheckAnomaly:
    """Tests for check_anomaly function."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)

        db = Database(path)
        db.init_schema()

        yield db

        os.unlink(path)

    def test_detects_anomaly_with_history(self, temp_db):
        """Test anomaly detection with previous source."""
        url = "https://example.com/test"

        with temp_db.get_connection() as conn:
            # Insert previous source
            conn.execute('''
                INSERT INTO sources (url, scraped_at, content_hash, record_count_extracted)
                VALUES (?, '2026-01-03T00:00:00Z', 'hash1', 100)
            ''', (url,))

            # Check anomaly with new count of 69 (31% drop)
            is_anomaly, info = check_anomaly(conn, url, 69, 0.30)

            assert is_anomaly is True
            assert info['prev_count'] == 100
            assert info['new_count'] == 69
            assert info['drop_ratio'] == 0.31
            assert info['threshold'] == 0.30

    def test_no_anomaly_without_history(self, temp_db):
        """Test no anomaly when no previous source exists."""
        url = "https://example.com/test"

        with temp_db.get_connection() as conn:
            # Check anomaly without any history
            is_anomaly, info = check_anomaly(conn, url, 50, 0.30)

            assert is_anomaly is False
            assert info['prev_count'] is None
            assert info['new_count'] == 50
            assert info['drop_ratio'] is None


class TestComputeFinalExitCode:
    """Tests for compute_final_exit_code function."""

    def test_exit_code_0_success(self):
        """Test exit code 0 for success."""
        exit_code = compute_final_exit_code(has_fatal=False, has_anomaly=False)
        assert exit_code == 0

    def test_exit_code_2_anomaly(self):
        """Test exit code 2 when anomaly detected."""
        exit_code = compute_final_exit_code(has_fatal=False, has_anomaly=True)
        assert exit_code == 2

    def test_exit_code_0_anomaly_suppressed(self):
        """Test exit code 0 when anomaly detected but suppressed."""
        exit_code = compute_final_exit_code(
            has_fatal=False,
            has_anomaly=True,
            no_anomaly_exit=True
        )
        assert exit_code == 0

    def test_exit_code_3_fatal(self):
        """Test exit code 3 when fatal error occurs."""
        exit_code = compute_final_exit_code(has_fatal=True, has_anomaly=False)
        assert exit_code == 3

    def test_exit_code_3_fatal_overrides_anomaly(self):
        """Test exit code 3 when both fatal and anomaly (fatal takes priority)."""
        exit_code = compute_final_exit_code(
            has_fatal=True,
            has_anomaly=True,
            no_anomaly_exit=False
        )
        assert exit_code == 3

    def test_exit_code_3_fatal_overrides_suppressed_anomaly(self):
        """Test exit code 3 when both fatal and suppressed anomaly."""
        exit_code = compute_final_exit_code(
            has_fatal=True,
            has_anomaly=True,
            no_anomaly_exit=True
        )
        assert exit_code == 3


class TestFormatMessages:
    """Tests for message formatting functions."""

    def test_format_anomaly_message(self):
        """Test anomaly message formatting."""
        url = "https://example.com/test"
        info = {
            'prev_count': 100,
            'new_count': 69,
            'drop_ratio': 0.31,
            'threshold': 0.30
        }

        message = format_anomaly_message(url, info)

        assert "ANOMALY" in message
        assert url in message
        assert "prev=100" in message
        assert "new=69" in message
        assert "drop=31.00%" in message
        assert "threshold=30.00%" in message

    def test_format_fatal_error_message_with_strategy(self):
        """Test fatal error message formatting with strategy."""
        url = "https://example.com/test"
        reason = "Connection timeout"
        strategy = "B"

        message = format_fatal_error_message(url, reason, strategy)

        assert "ERROR" in message
        assert url in message
        assert "scrape_failed" in message
        assert reason in message
        assert "strategy=B" in message

    def test_format_fatal_error_message_no_strategy(self):
        """Test fatal error message formatting without strategy."""
        url = "https://example.com/test"
        reason = "Parse error"

        message = format_fatal_error_message(url, reason, None)

        assert "ERROR" in message
        assert url in message
        assert "scrape_failed" in message
        assert reason in message
        assert "strategy=none" in message
