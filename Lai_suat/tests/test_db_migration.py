"""Tests for database migration and schema compatibility."""

import pytest
import tempfile
import os
from app.db import Database


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    db = Database(path)
    db.init_schema()  # This calls ensure_schema

    yield db

    # Cleanup
    os.unlink(path)


def test_schema_has_sources_columns(temp_db):
    """Test that sources table has all required columns after migration."""
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(sources)")
        columns = {row['name'] for row in cursor.fetchall()}

        # Check all new columns exist
        assert 'strategy_used' in columns
        assert 'parse_version' in columns
        assert 'http_status' in columns
        assert 'fetched_at' in columns
        assert 'record_count_extracted' in columns
        assert 'record_count_inserted' in columns
        assert 'dropped_duplicate_count' in columns
        assert 'dropped_invalid_count' in columns
        assert 'dropped_reason_json' in columns

        # Check original columns still exist
        assert 'id' in columns
        assert 'url' in columns
        assert 'scraped_at' in columns
        assert 'content_hash' in columns
        assert 'page_updated_text' in columns


def test_schema_has_observations_columns(temp_db):
    """Test that observations table has all required columns after migration."""
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(observations)")
        columns = {row['name'] for row in cursor.fetchall()}

        # Check new columns exist
        assert 'raw_value' in columns
        assert 'parse_warnings' in columns

        # Check original columns still exist
        assert 'id' in columns
        assert 'source_id' in columns
        assert 'bank_id' in columns
        assert 'series_id' in columns
        assert 'term_id' in columns
        assert 'rate_min_pct' in columns
        assert 'rate_max_pct' in columns
        assert 'rate_pct' in columns


def test_insert_source_with_metadata(temp_db):
    """Test that insert_source accepts new metadata parameters."""
    source_id = temp_db.insert_source(
        url="https://example.com",
        scraped_at="2026-01-04T00:00:00Z",
        content_hash="abc123",
        page_updated_text="Updated 1/2026",
        strategy_used="A",
        parse_version="1.0",
        http_status=200,
        fetched_at="2026-01-04T00:00:01Z",
        record_count_extracted=100,
        record_count_inserted=95,
        dropped_duplicate_count=3,
        dropped_invalid_count=2,
        dropped_reason_json='{"missing_bank": 1, "out_of_range": 1}'
    )

    assert source_id > 0

    # Verify data was inserted correctly
    source = temp_db.get_source(source_id)
    assert source['strategy_used'] == "A"
    assert source['parse_version'] == "1.0"
    assert source['http_status'] == 200
    assert source['record_count_extracted'] == 100
    assert source['record_count_inserted'] == 95
    assert source['dropped_duplicate_count'] == 3
    assert source['dropped_invalid_count'] == 2
    assert source['dropped_reason_json'] == '{"missing_bank": 1, "out_of_range": 1}'


def test_insert_observation_with_metadata(temp_db):
    """Test that insert_observation accepts raw_value and parse_warnings."""
    # First insert a source and other dependencies
    source_id = temp_db.insert_source(
        url="https://example.com",
        scraped_at="2026-01-04T00:00:00Z",
        content_hash="abc123"
    )
    bank_id = temp_db.upsert_bank("Test Bank")
    series_id = temp_db.upsert_series("deposit", "deposit_tai_quay")
    term_id = temp_db.upsert_term("6 tháng", 6)

    obs_id = temp_db.insert_observation(
        source_id=source_id,
        bank_id=bank_id,
        series_id=series_id,
        term_id=term_id,
        rate_min_pct=5.0,
        rate_max_pct=5.0,
        rate_pct=5.0,
        raw_value="5.0%",
        parse_warnings='[]'
    )

    assert obs_id is not None

    # Verify data was inserted
    observations = temp_db.get_observations_by_source(source_id)
    assert len(observations) == 1
    assert observations[0]['raw_value'] == "5.0%"
    assert observations[0]['parse_warnings'] == '[]'


def test_backward_compatible_insert_source(temp_db):
    """Test that insert_source works without new metadata (backward compatible)."""
    # Old-style call without new parameters
    source_id = temp_db.insert_source(
        url="https://example.com",
        scraped_at="2026-01-04T00:00:00Z",
        content_hash="abc123",
        page_updated_text="Updated 1/2026"
    )

    assert source_id > 0

    # Verify source was created with NULL for new columns
    source = temp_db.get_source(source_id)
    assert source['strategy_used'] is None
    assert source['parse_version'] is None
    assert source['http_status'] is None
    assert source['record_count_extracted'] is None


def test_backward_compatible_insert_observation(temp_db):
    """Test that insert_observation works without new metadata (backward compatible)."""
    # Setup dependencies
    source_id = temp_db.insert_source(
        url="https://example.com",
        scraped_at="2026-01-04T00:00:00Z",
        content_hash="abc123"
    )
    bank_id = temp_db.upsert_bank("Test Bank")
    series_id = temp_db.upsert_series("deposit", "deposit_tai_quay")
    term_id = temp_db.upsert_term("6 tháng", 6)

    # Old-style call without new parameters
    obs_id = temp_db.insert_observation(
        source_id=source_id,
        bank_id=bank_id,
        series_id=series_id,
        term_id=term_id,
        rate_min_pct=5.0,
        rate_max_pct=5.0,
        rate_pct=5.0
    )

    assert obs_id is not None

    # Verify observation was created with NULL for new columns
    observations = temp_db.get_observations_by_source(source_id)
    assert len(observations) == 1
    assert observations[0]['raw_value'] is None
    assert observations[0]['parse_warnings'] is None
