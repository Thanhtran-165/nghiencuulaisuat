"""Tests for FastAPI /latest endpoint with merged multi-source data."""

import pytest
import tempfile
import os
import sys

# Add backend to Python path for imports
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.db import Database, get_connection


@pytest.fixture(scope="module")
def test_db_with_merged_data():
    """
    Create a test database with merged multi-source data for API testing.

    This fixture sets up:
    - 2 sources (timo and 24hmoney) with different priorities
    - Same bank+term+series with different rates
    - Verifies /latest endpoint returns data from highest priority source
    """
    # Create temp database
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    # Import Database class to init schema
    from app.db import Database
    db = Database(path)
    db.init_schema()

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Create test data: VCB 12-month deposit
        cursor.execute("INSERT INTO banks (name) VALUES ('VCB')")
        vcb_id = cursor.lastrowid

        cursor.execute("INSERT INTO series (product_group, code) VALUES ('deposit', 'deposit_tai_quay')")
        series_id = cursor.lastrowid

        cursor.execute("INSERT INTO terms (label, months) VALUES ('12 tháng', 12)")
        term_id = cursor.lastrowid

        # Insert source 1 (timo, priority=1, rate=5.0%)
        cursor.execute('''
            INSERT INTO sources (url, scraped_at, content_hash)
            VALUES ('https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/', '2026-01-05T10:00:00Z', 'hash1')
        ''')
        timo_source_id = cursor.lastrowid

        # Insert source 2 (24hmoney, priority=2, rate=4.8%)
        cursor.execute('''
            INSERT INTO sources (url, scraped_at, content_hash)
            VALUES ('https://24hmoney.vn/lai-suat-gui-ngan-hang', '2026-01-05T10:00:00Z', 'hash2')
        ''')
        money_24h_source_id = cursor.lastrowid

        # Insert observations from both sources
        cursor.execute('''
            INSERT INTO observations (source_id, bank_id, series_id, term_id, rate_pct, rate_min_pct, rate_max_pct)
            VALUES (?, ?, ?, ?, 5.0, 5.0, 5.0)
        ''', (timo_source_id, vcb_id, series_id, term_id))

        cursor.execute('''
            INSERT INTO observations (source_id, bank_id, series_id, term_id, rate_pct, rate_min_pct, rate_max_pct)
            VALUES (?, ?, ?, ?, 4.8, 4.8, 4.8)
        ''', (money_24h_source_id, vcb_id, series_id, term_id))

        conn.commit()

        # Verify merged view returns timo's rate (priority=1)
        cursor.execute('''
            SELECT rate_pct, source_url, source_priority
            FROM v_latest_observations_merged
            WHERE bank_name = 'VCB' AND series_code = 'deposit_tai_quay'
        ''')
        result = cursor.fetchone()

        assert result is not None, "Merged view should have VCB data"
        assert result['rate_pct'] == 5.0, f"Should select timo's rate (5.0), got {result['rate_pct']}"
        assert result['source_priority'] == 1, "Should have priority 1"
        assert 'timo.vn' in result['source_url'], "Should be from timo source"

        yield path

    finally:
        conn.close()
        os.unlink(path)


def test_latest_endpoint_uses_merged_view(test_db_with_merged_data):
    """
    Test that /latest endpoint uses merged view and returns canonical data.

    This test requires the FastAPI app to be running.
    Skip if backend is not available.
    """
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

    # Set env to use test database
    os.environ['DB_PATH'] = test_db_with_merged_data

    try:
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        # Query /latest for VCB deposit_tai_quay 12-month
        response = client.get("/latest?series_code=deposit_tai_quay&term_months=12")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert 'rows' in data
        assert 'meta' in data

        # Find VCB row
        vcb_row = None
        for row in data['rows']:
            if row['bank_name'] == 'VCB':
                vcb_row = row
                break

        assert vcb_row is not None, "Should have VCB in results"

        # Verify it's timo's rate (priority=1)
        assert vcb_row['rate_pct'] == 5.0, f"Should be 5.0% from timo, got {vcb_row['rate_pct']}"
        assert vcb_row['source_priority'] == 1, "Should have priority 1"
        assert 'timo.vn' in vcb_row['source_url'], "Should be from timo"

        print("✅ /latest endpoint correctly uses merged view")

    except ImportError as e:
        pytest.skip(f"FastAPI not available: {e}")
    except Exception as e:
        pytest.fail(f"API test failed: {e}")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
