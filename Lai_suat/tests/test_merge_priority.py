"""Tests for multi-source merge by priority."""

import pytest
import os
import tempfile
from app.db import Database


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    db = Database(path)
    db.init_schema()
    yield db
    os.unlink(path)


def test_seed_source_priorities(temp_db):
    """Test that source priorities are seeded correctly."""
    # Check that priorities exist
    timo_deposit_priority = temp_db.get_source_priority(
        'https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/'
    )
    assert timo_deposit_priority == 1, "Timo deposit should have priority 1"

    timo_loan_priority = temp_db.get_source_priority(
        'https://timo.vn/blogs/lai-suat-vay-tin-chap-ngan-hang-nao-cao-nhat/'
    )
    assert timo_loan_priority == 1, "Timo loan should have priority 1"

    money_24h_priority = temp_db.get_source_priority(
        'https://24hmoney.vn/lai-suat-gui-ngan-hang'
    )
    assert money_24h_priority == 2, "24hmoney should have priority 2"


def test_update_source_priority(temp_db):
    """Test updating source priority."""
    url = 'https://24hmoney.vn/lai-suat-gui-ngan-hang'

    # Update priority
    temp_db.update_source_priority(url, 3, 'Updated priority for testing')

    # Check updated priority
    priority = temp_db.get_source_priority(url)
    assert priority == 3, "Priority should be updated to 3"


def test_merge_priority_selects_highest_priority_source(temp_db):
    """
    Test merge logic: when multiple sources have data for same bank+term+series,
    view merged should select record from source with lowest priority number.
    """
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()

        # Create test data: 2 sources, same bank+term+series, different rates
        # Insert banks
        cursor.execute("INSERT INTO banks (name) VALUES ('VCB')")
        vcb_id = cursor.lastrowid

        # Insert series
        cursor.execute("INSERT INTO series (product_group, code) VALUES ('deposit', 'deposit_tai_quay')")
        series_id = cursor.lastrowid

        # Insert terms
        cursor.execute("INSERT INTO terms (label, months) VALUES ('12 tháng', 12)")
        term_id = cursor.lastrowid

        # Insert source 1 (timo, priority=1)
        cursor.execute('''
            INSERT INTO sources (url, scraped_at, content_hash)
            VALUES ('https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/', '2026-01-05T10:00:00Z', 'hash1')
        ''')
        source_1_id = cursor.lastrowid

        # Insert source 2 (24hmoney, priority=2)
        cursor.execute('''
            INSERT INTO sources (url, scraped_at, content_hash)
            VALUES ('https://24hmoney.vn/lai-suat-gui-ngan-hang', '2026-01-05T10:00:00Z', 'hash2')
        ''')
        source_2_id = cursor.lastrowid

        # Insert observations from both sources (same bank+term+series)
        # Source 1 (timo): rate = 5.0%
        cursor.execute('''
            INSERT INTO observations (source_id, bank_id, series_id, term_id, rate_pct, rate_min_pct, rate_max_pct)
            VALUES (?, ?, ?, ?, 5.0, 5.0, 5.0)
        ''', (source_1_id, vcb_id, series_id, term_id))

        # Source 2 (24hmoney): rate = 4.8%
        cursor.execute('''
            INSERT INTO observations (source_id, bank_id, series_id, term_id, rate_pct, rate_min_pct, rate_max_pct)
            VALUES (?, ?, ?, ?, 4.8, 4.8, 4.8)
        ''', (source_2_id, vcb_id, series_id, term_id))

    # Query merged view
    merged_records = temp_db.get_latest_observations_merged()

    # Should only have 1 record (not 2), from timo (priority=1)
    assert len(merged_records) == 1, "Should merge to single record"

    record = merged_records[0]
    assert record['bank_name'] == 'VCB'
    assert record['series_code'] == 'deposit_tai_quay'
    assert record['term_months'] == 12

    # Should select timo's rate (5.0%) since priority=1 > priority=2
    assert record['rate_pct'] == 5.0, f"Should select timo's rate (5.0%), got {record['rate_pct']}"
    assert 'timo.vn' in record['source_url'], "Should select timo as source"
    assert record['source_priority'] == 1, "Should have priority 1"


def test_merge_priority_with_tiebreaker_scraped_at(temp_db):
    """
    Test tiebreaker: when priorities are equal, select most recent scraped_at.
    """
    # First insert all data
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()

        # Create test data
        cursor.execute("INSERT INTO banks (name) VALUES ('VCB')")
        vcb_id = cursor.lastrowid

        cursor.execute("INSERT INTO series (product_group, code) VALUES ('deposit', 'deposit_tai_quay')")
        series_id = cursor.lastrowid

        cursor.execute("INSERT INTO terms (label, months) VALUES ('12 tháng', 12)")
        term_id = cursor.lastrowid

        # Insert source 1 (older)
        cursor.execute('''
            INSERT INTO sources (url, scraped_at, content_hash)
            VALUES ('https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/', '2026-01-04T10:00:00Z', 'hash1')
        ''')
        source_1_id = cursor.lastrowid

        # Insert source 2 (newer)
        cursor.execute('''
            INSERT INTO sources (url, scraped_at, content_hash)
            VALUES ('https://24hmoney.vn/lai-suat-gui-ngan-hang', '2026-01-05T10:00:00Z', 'hash2')
        ''')
        source_2_id = cursor.lastrowid

        # Insert observations
        cursor.execute('''
            INSERT INTO observations (source_id, bank_id, series_id, term_id, rate_pct, rate_min_pct, rate_max_pct)
            VALUES (?, ?, ?, ?, 5.0, 5.0, 5.0)
        ''', (source_1_id, vcb_id, series_id, term_id))

        cursor.execute('''
            INSERT INTO observations (source_id, bank_id, series_id, term_id, rate_pct, rate_min_pct, rate_max_pct)
            VALUES (?, ?, ?, ?, 4.8, 4.8, 4.8)
        ''', (source_2_id, vcb_id, series_id, term_id))

    # Then update priorities in separate transaction (avoid DB lock)
    temp_db.update_source_priority('https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/', 1)
    temp_db.update_source_priority('https://24hmoney.vn/lai-suat-gui-ngan-hang', 1)

    # Query merged view
    merged_records = temp_db.get_latest_observations_merged()

    # Should select 24hmoney (more recent) due to tiebreaker
    assert len(merged_records) == 1
    record = merged_records[0]
    assert '24hmoney.vn' in record['source_url'], "Should select 24hmoney (more recent)"


def test_swap_priorities_changes_selection(temp_db):
    """
    Test that swapping priorities changes which source is selected in merged view.
    """
    # Insert all data first
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()

        # Setup same as first test
        cursor.execute("INSERT INTO banks (name) VALUES ('VCB')")
        vcb_id = cursor.lastrowid

        cursor.execute("INSERT INTO series (product_group, code) VALUES ('deposit', 'deposit_tai_quay')")
        series_id = cursor.lastrowid

        cursor.execute("INSERT INTO terms (label, months) VALUES ('12 tháng', 12)")
        term_id = cursor.lastrowid

        cursor.execute('''
            INSERT INTO sources (url, scraped_at, content_hash)
            VALUES ('https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/', '2026-01-05T10:00:00Z', 'hash1')
        ''')
        source_1_id = cursor.lastrowid

        cursor.execute('''
            INSERT INTO sources (url, scraped_at, content_hash)
            VALUES ('https://24hmoney.vn/lai-suat-gui-ngan-hang', '2026-01-05T10:00:00Z', 'hash2')
        ''')
        source_2_id = cursor.lastrowid

        cursor.execute('''
            INSERT INTO observations (source_id, bank_id, series_id, term_id, rate_pct, rate_min_pct, rate_max_pct)
            VALUES (?, ?, ?, ?, 5.0, 5.0, 5.0)
        ''', (source_1_id, vcb_id, series_id, term_id))

        cursor.execute('''
            INSERT INTO observations (source_id, bank_id, series_id, term_id, rate_pct, rate_min_pct, rate_max_pct)
            VALUES (?, ?, ?, ?, 4.8, 4.8, 4.8)
        ''', (source_2_id, vcb_id, series_id, term_id))

    # Initial: timo priority=1, 24hmoney priority=2 (seeded by init_schema)
    # Should select timo
    merged_records = temp_db.get_latest_observations_merged()
    assert merged_records[0]['rate_pct'] == 5.0, "Should select timo initially"

    # Swap priorities
    temp_db.update_source_priority('https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/', 3)
    temp_db.update_source_priority('https://24hmoney.vn/lai-suat-gui-ngan-hang', 2)

    # Now should select 24hmoney (priority=2 < priority=3)
    merged_records = temp_db.get_latest_observations_merged()
    assert merged_records[0]['rate_pct'] == 4.8, "Should select 24hmoney after swap"
    assert '24hmoney.vn' in merged_records[0]['source_url'], "Source should be 24hmoney"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
