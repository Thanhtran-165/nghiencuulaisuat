"""
Tests for database schema and operations
"""
import pytest
from datetime import date

from app.db.schema import DatabaseManager


def test_database_initialization(temp_db):
    """Test that database tables are created correctly"""
    # Check that tables exist
    result = temp_db.con.execute("SHOW TABLES").fetchall()
    table_names = [row[0] for row in result]

    assert 'gov_yield_curve' in table_names
    assert 'gov_yield_change_stats' in table_names
    assert 'interbank_rates' in table_names
    assert 'ingest_runs' in table_names


def test_insert_yield_curve(temp_db, sample_yield_curve_data):
    """Test inserting yield curve data"""
    count = temp_db.insert_yield_curve(sample_yield_curve_data)

    assert count == len(sample_yield_curve_data)

    # Verify data was inserted
    result = temp_db.con.execute("SELECT COUNT(*) FROM gov_yield_curve").fetchone()
    assert result[0] == len(sample_yield_curve_data)


def test_yield_curve_upsert(temp_db):
    """Test that upsert works correctly (no duplicates)"""
    data = [{
        'date': '2024-01-15',
        'tenor_label': '2Y',
        'tenor_days': 730,
        'spot_rate_continuous': 5.25,
        'par_yield': 5.30,
        'spot_rate_annual': 5.28,
        'source': 'TEST',
        'fetched_at': '2024-01-15T10:00:00'
    }]

    # Insert first time
    temp_db.insert_yield_curve(data)
    result = temp_db.con.execute("SELECT COUNT(*) FROM gov_yield_curve").fetchone()
    assert result[0] == 1

    # Insert again (should update, not insert duplicate)
    data[0]['spot_rate_annual'] = 5.50
    temp_db.insert_yield_curve(data)
    result = temp_db.con.execute("SELECT COUNT(*) FROM gov_yield_curve").fetchone()
    assert result[0] == 1  # Still 1 row

    # Verify the value was updated
    result = temp_db.con.execute(
        "SELECT spot_rate_annual FROM gov_yield_curve WHERE tenor_label = '2Y'"
    ).fetchone()
    assert result[0] == 5.50


def test_insert_interbank_rates(temp_db, sample_interbank_data):
    """Test inserting interbank rate data"""
    count = temp_db.insert_interbank_rates(sample_interbank_data)

    assert count == len(sample_interbank_data)

    # Verify data was inserted
    result = temp_db.con.execute("SELECT COUNT(*) FROM interbank_rates").fetchone()
    assert result[0] == len(sample_interbank_data)


def test_get_latest_yield_curve(temp_db, sample_yield_curve_data):
    """Test retrieving latest yield curve"""
    temp_db.insert_yield_curve(sample_yield_curve_data)

    result = temp_db.get_latest_yield_curve()

    assert len(result) == len(sample_yield_curve_data)
    assert result[0]['tenor_label'] == '2Y'


def test_get_interbank_rates(temp_db, sample_interbank_data):
    """Test retrieving interbank rates with filters"""
    temp_db.insert_interbank_rates(sample_interbank_data)

    # Get all
    result = temp_db.get_interbank_rates()
    assert len(result) == len(sample_interbank_data)

    # Filter by tenor
    result = temp_db.get_interbank_rates(tenor='ON')
    assert len(result) == 1
    assert result[0]['tenor_label'] == 'ON'


def test_ingest_run_logging(temp_db):
    """Test logging of ingest runs"""
    run_id = temp_db.log_ingest_run(
        provider='test_provider',
        start_date='2024-01-01',
        end_date='2024-01-31',
        status='running'
    )

    assert run_id is not None

    # Update run
    temp_db.update_ingest_run(
        run_id=run_id,
        status='completed',
        rows_inserted=100
    )

    # Verify
    result = temp_db.con.execute(
        "SELECT status, rows_inserted FROM ingest_runs WHERE id = ?",
        [run_id]
    ).fetchone()

    assert result[0] == 'completed'
    assert result[1] == 100
