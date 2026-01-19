#!/usr/bin/env python3
"""Migration runner for interest rates database."""

import sys
import sqlite3
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.settings import get_settings

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def check_column_exists(cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns

def check_index_exists(cursor, index_name: str) -> bool:
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='index' AND name='{index_name}'")
    return cursor.fetchone() is not None

def check_table_exists(cursor, table_name: str) -> bool:
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
    return cursor.fetchone() is not None

def ensure_migrations_table(cursor):
    if not check_table_exists(cursor, 'schema_migrations'):
        logger.info("Creating schema_migrations table...")
        cursor.execute("""
            CREATE TABLE schema_migrations (
                migration_name TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        logger.info("✅ schema_migrations table created")

def is_migration_applied(cursor, migration_name: str) -> bool:
    cursor.execute("SELECT 1 FROM schema_migrations WHERE migration_name = ?", (migration_name,))
    return cursor.fetchone() is not None

def record_migration(cursor, migration_name: str):
    from datetime import datetime
    applied_at = datetime.utcnow().isoformat()
    cursor.execute("INSERT INTO schema_migrations (migration_name, applied_at) VALUES (?, ?)",
                   (migration_name, applied_at))
    logger.info(f"✅ Migration '{migration_name}' recorded as applied at {applied_at}")

def run_migration_idempotent(migration_file: str):
    settings = get_settings()
    migration_name = migration_file.replace('.sql', '')
    logger.info(f"Checking migration '{migration_name}'...")

    conn = sqlite3.connect(settings.DB_PATH)
    cursor = conn.cursor()

    try:
        ensure_migrations_table(cursor)
        conn.commit()

        if is_migration_applied(cursor, migration_name):
            logger.info(f"ℹ️  Migration '{migration_name}' already applied, skipping")
            return

        logger.info(f"Applying migration '{migration_name}'...")
        
        migration_path = Path(__file__).parent / migration_file
        with open(migration_path, 'r') as f:
            sql = f.read()
        
        cursor.executescript(sql)
        conn.commit()
        record_migration(cursor, migration_name)
        conn.commit()

        logger.info(f"✅ Migration '{migration_name}' completed successfully")

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Migration '{migration_file}' FAILED: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 -m app.migrations.run_migration <migration_file.sql>")
        sys.exit(1)
    run_migration_idempotent(sys.argv[1])
