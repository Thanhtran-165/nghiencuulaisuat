"""Tests for idempotent seed operations."""

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


def test_seed_source_priorities_is_idempotent(temp_db):
    """
    Test that seed_source_priorities() can be run multiple times safely.

    Requirements:
    - First run: inserts default priorities
    - Second run: does NOT override manually updated priorities
    - Does NOT insert duplicate rows
    """
    # First seed
    temp_db.seed_source_priorities()

    with temp_db.get_connection() as conn:
        cursor = conn.cursor()

        # Check initial state
        cursor.execute("SELECT COUNT(*) as count FROM source_priorities")
        initial_count = cursor.fetchone()['count']
        assert initial_count == 3, f"Should have 3 priorities, got {initial_count}"

        # Manually update one priority
        cursor.execute('''
            UPDATE source_priorities
            SET priority = 99, notes = 'Manually updated'
            WHERE url = 'https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/'
        ''')

        cursor.execute("SELECT priority FROM source_priorities WHERE url = ?", ('https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/',))
        manual_priority = cursor.fetchone()['priority']
        assert manual_priority == 99, "Manual update should succeed"

    # Second seed (should NOT override manual update)
    temp_db.seed_source_priorities()

    with temp_db.get_connection() as conn:
        cursor = conn.cursor()

        # Count should still be 3 (no duplicates)
        cursor.execute("SELECT COUNT(*) as count FROM source_priorities")
        final_count = cursor.fetchone()['count']
        assert final_count == 3, f"Should still have 3 priorities (no duplicates), got {final_count}"

        # Manual priority should be preserved
        cursor.execute("SELECT priority, notes FROM source_priorities WHERE url = ?", ('https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/',))
        result = cursor.fetchone()
        assert result['priority'] == 99, "Manual priority should be preserved after second seed"
        assert result['notes'] == 'Manually updated', "Manual notes should be preserved"


def test_seed_does_not_insert_duplicates(temp_db):
    """Test that running seed twice doesn't create duplicate rows."""
    # Run seed twice
    temp_db.seed_source_priorities()
    temp_db.seed_source_priorities()

    with temp_db.get_connection() as conn:
        cursor = conn.cursor()

        # Check for duplicate URLs
        cursor.execute('''
            SELECT url, COUNT(*) as count
            FROM source_priorities
            GROUP BY url
            HAVING count > 1
        ''')
        duplicates = cursor.fetchall()

        assert len(duplicates) == 0, f"Should have no duplicate URLs, found {len(duplicates)}"

        # Should still have exactly 3 rows
        cursor.execute("SELECT COUNT(*) as count FROM source_priorities")
        count = cursor.fetchone()['count']
        assert count == 3, f"Should have exactly 3 rows, got {count}"


def test_init_db_idempotent(temp_db):
    """Test that init_db() can be run multiple times safely."""
    # Get initial counts
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM source_priorities")
        initial_count = cursor.fetchone()['count']

    # Run init_schema again (simulating running init-db twice)
    temp_db.init_schema()

    # Check counts haven't changed
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM source_priorities")
        final_count = cursor.fetchone()['count']

        assert initial_count == final_count, "init_schema should be idempotent"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
