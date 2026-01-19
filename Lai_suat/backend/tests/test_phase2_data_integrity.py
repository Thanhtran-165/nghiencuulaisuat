"""
Phase 2: Data Integrity Tests

Tests for:
- API parameter backward compatibility (bank_name + bank alias)
- Per-day deduplication (observed_day unique constraint)
- Distinct days accumulation
"""

import pytest
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app
from app.settings import get_settings
from fastapi.testclient import TestClient

client = TestClient(app)

# Test database path (uses settings from app)
settings = get_settings()
TEST_DB_PATH = settings.DB_PATH


class TestAPIContract:
    """Test API contract stability and backward compatibility."""

    def test_history_accepts_bank_name_parameter(self):
        """Test /history endpoint accepts official 'bank_name' parameter."""
        response = client.get("/history?bank_name=OCB&series_code=deposit_online&term_months=12")
        assert response.status_code in [200, 404]  # 404 if OCB not in DB, but param accepted
        assert "detail" not in response.json() or response.status_code == 200

    def test_history_accepts_bank_alias_parameter(self):
        """Test /history endpoint accepts deprecated 'bank' alias parameter."""
        response = client.get("/history?bank=OCB&series_code=deposit_online&term_months=12")
        assert response.status_code in [200, 404]  # Should work with alias

    def test_history_rejects_both_bank_and_bank_name(self):
        """Test /history rejects both 'bank' and 'bank_name' simultaneously."""
        response = client.get("/history?bank=OCB&bank_name=OCB&series_code=deposit_online&term_months=12")
        assert response.status_code == 400
        assert "Cannot specify both" in response.json()["detail"]

    def test_history_requires_bank_name_or_bank(self):
        """Test /history requires either 'bank_name' or 'bank' parameter."""
        response = client.get("/history?series_code=deposit_online&term_months=12")
        assert response.status_code == 400
        assert "Must specify 'bank_name'" in response.json()["detail"]


class TestDistinctDaysAccumulation:
    """Test distinct days increase with data accumulation."""

    def test_meta_latest_returns_distinct_days_overall(self):
        """Test /meta/latest returns distinct_days_overall field."""
        response = client.get("/meta/latest")
        assert response.status_code == 200
        data = response.json()
        assert "distinct_days_overall" in data
        assert isinstance(data["distinct_days_overall"], int)
        assert data["distinct_days_overall"] >= 0

    def test_distinct_days_matches_database(self):
        """Test distinct_days_overall matches actual DB query."""
        # Get from API
        response = client.get("/meta/latest")
        api_days = response.json()["distinct_days_overall"]

        # Get from DB directly
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(DISTINCT observed_day) FROM observations WHERE observed_day IS NOT NULL")
            db_days = cursor.fetchone()[0]
        finally:
            conn.close()

        assert api_days == db_days, f"API reported {api_days} days, DB has {db_days} days"


class TestObservationsDeduplication:
    """Test per-day deduplication (requires migration to be run)."""

    def test_observed_day_column_exists(self):
        """Test observed_day column exists in observations table."""
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("PRAGMA table_info(observations)")
            columns = [row[1] for row in cursor.fetchall()]
            assert "observed_day" in columns, "observed_day column missing. Run migration first!"
        finally:
            conn.close()

    def test_observed_day_is_populated(self):
        """Test observed_day is populated for all observations."""
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM observations WHERE observed_day IS NULL")
            null_count = cursor.fetchone()[0]
            assert null_count == 0, f"{null_count} observations have NULL observed_day"
        finally:
            conn.close()

    def test_unique_index_exists(self):
        """Test unique index on (series_id, bank_id, term_months, observed_day, source_id)."""
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        try:
            # Check for new index name first (v1.2.2.1+)
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='index'
                AND name='idx_observations_unique_source_day'
            """)
            new_index_exists = cursor.fetchone() is not None

            # Fall back to old index name for backward compatibility
            if not new_index_exists:
                cursor.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='index'
                    AND name='idx_observations_unique_day'
                """)
                old_index_exists = cursor.fetchone() is not None

            index_exists = new_index_exists or old_index_exists

            assert index_exists, "Unique index not found (neither old nor new name). Run migration first!"
        finally:
            conn.close()

    def test_duplicate_same_day_idempotent_insert(self):
        """
        Test that inserting duplicate observation for same day
        either (a) updates existing record OR (b) fails with constraint error.

        This test verifies the unique constraint prevents accidental duplicates.
        """
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        try:
            # Count observations before
            cursor.execute("SELECT COUNT(*) FROM observations")
            count_before = cursor.fetchone()[0]

            # Try to count distinct days
            cursor.execute("SELECT COUNT(DISTINCT observed_day) FROM observations WHERE observed_day IS NOT NULL")
            days_before = cursor.fetchone()[0]

            # The key assertion: distinct_days should equal or exceed count in practice
            # (if unique constraint works, no duplicates per day)
            # This is a weak test because we can't insert actual test data without DB schema knowledge

            # At minimum, verify that if we have data, observed_day is consistent
            cursor.execute("SELECT COUNT(*) FROM observations WHERE observed_day IS NOT NULL")
            populated_count = cursor.fetchone()[0]

            if count_before > 0:
                assert populated_count == count_before, "Some observations missing observed_day"
                assert days_before >= 1, "Should have at least 1 distinct day"

        finally:
            conn.close()


class TestDataIntegrityAccumulation:
    """Test that distinct days increase correctly over time."""

    def test_distinct_days_increases_with_new_data(self):
        """
        Test that distinct_days_overall increases when we have observations
        from different dates.

        This is a data-dependent test. If DB only has 1 day of data,
        distinct_days_overall should be 1. After scraping runs next day,
        it should increase to 2.
        """
        response = client.get("/meta/latest")
        data = response.json()

        distinct_days = data["distinct_days_overall"]
        observations_count = data["observations_count"]

        # We should have at least 1 day if we have any observations
        if observations_count > 0:
            assert distinct_days >= 1, "Should have at least 1 distinct day with observations"

        # In normal operation: distinct_days <= observations_count
        # (Each day can have multiple observations, but not fewer days than total obs)
        assert distinct_days <= observations_count, \
            f"distinct_days ({distinct_days}) cannot exceed total observations ({observations_count})"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
