#!/usr/bin/env python3
"""
Phase 2.2.1: Rename unique index to reflect per-source-per-day semantics.

DEPRECATED: This script is now a wrapper for the SQL migration.
Please use the standard migration pathway instead:

    python3 -m app.migrations.run_migration phase2_2_1_rename_unique_index.sql

This wrapper remains for backward compatibility but will be removed in a future version.
"""

import sys
import os
import subprocess
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def run_migration():
    """Run the index rename migration via SQL migration pathway."""
    migration_sql = "phase2_2_1_rename_unique_index.sql"

    logger.warning("=" * 70)
    logger.warning("⚠️  DEPRECATED: This script is a wrapper for the SQL migration")
    logger.warning("⚠️  Please use: python3 -m app.migrations.run_migration phase2_2_1_rename_unique_index.sql")
    logger.warning("=" * 70)
    logger.info("")

    # Run the SQL migration via subprocess
    logger.info(f"Forwarding to: python3 -m app.migrations.run_migration {migration_sql}")

    # Get the correct paths
    # Script is in backend/app/migrations/, so we need to go up 3 levels to reach backend/
    backend_dir = Path(__file__).parent.parent.parent

    # Set up environment for subprocess
    env = dict(os.environ)
    env['PYTHONPATH'] = str(backend_dir)

    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.migrations.run_migration", migration_sql],
            cwd=str(backend_dir),
            env=env,
            check=True
        )
        sys.exit(result.returncode)
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Migration failed with exit code {e.returncode}")
        sys.exit(e.returncode)
    except Exception as e:
        logger.error(f"❌ Failed to run migration: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_migration()
