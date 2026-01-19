"""
Database health checks and migration verification.

Called on app startup to ensure database schema is up to date.
"""

import logging
import sqlite3
from .settings import get_settings

logger = logging.getLogger(__name__)


def check_database_health() -> dict:
    """
    Check database health and migration status.

    Returns health status dict with warnings if migrations are pending.
    """
    settings = get_settings()
    health = {
        "ok": True,
        "migrations_pending": [],
        "warnings": []
    }

    try:
        conn = sqlite3.connect(settings.DB_PATH)
        cursor = conn.cursor()

        # Check 1: migrations table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
        if not cursor.fetchone():
            health["ok"] = False
            health["warnings"].append("Schema migrations table not found. Run: python3 -m app.migrations.run_migration add_observed_day.sql")
            return health

        # Check 2: observed_day column exists
        cursor.execute("PRAGMA table_info(observations)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'observed_day' not in columns:
            health["migrations_pending"].append("add_observed_day")
            health["warnings"].append(
                "Column 'observed_day' missing in observations table. "
                "This is REQUIRED for data integrity. "
                "Run: python3 -m app.migrations.run_migration add_observed_day.sql"
            )

        # Check 3: unique index exists (accept old or new name for backward compatibility)
        new_index = "idx_observations_unique_source_day"
        old_index = "idx_observations_unique_day"

        has_new_index = check_table_exists(cursor, new_index)  # This function actually checks indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name=?", (new_index,))
        has_new_index = cursor.fetchone()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name=?", (old_index,))
        has_old_index = cursor.fetchone()

        if not has_new_index and not has_old_index:
            health["migrations_pending"].append("add_observed_day")
            health["warnings"].append(
                "Unique index not found. "
                "This is REQUIRED to prevent duplicate observations per day. "
                "Run: python3 -m app.migrations.run_migration phase2_2_1_rename_unique_index.sql"
            )
        elif has_old_index and not has_new_index:
            health["warnings"].append(
                f"Legacy index name '{old_index}' detected. Consider running: python3 -m app.migrations.run_migration phase2_2_1_rename_unique_index.sql"
            )

        # Check 4: performance index exists (optional but recommended)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_observations_observed_day'")
        if not cursor.fetchone():
            health["warnings"].append(
                "Performance index 'idx_observations_observed_day' not found (optional but recommended). "
                "Run: python3 -m app.migrations.run_migration add_observed_day.sql"
            )

        conn.close()

        if health["migrations_pending"]:
            logger.warning("⚠️  DATABASE MIGRATIONS PENDING:")
            for warning in health["warnings"]:
                logger.warning(f"   - {warning}")

        return health

    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "ok": False,
            "error": str(e),
            "migrations_pending": ["unknown"],
            "warnings": [f"Database health check failed: {e}"]
        }
