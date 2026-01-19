"""
Ops Manager for backup/restore/export/import operations

Provides safe database operations with proper safeguards.
"""
import os
import shutil
import logging
import csv
from pathlib import Path
from typing import Optional, List
from datetime import date

logger = logging.getLogger(__name__)


class OpsManager:
    """Manages database backup, restore, export, and import operations"""

    def __init__(self, db_path: str):
        """
        Initialize ops manager

        Args:
            db_path: Path to DuckDB database file
        """
        self.db_path = Path(db_path)

    def backup(self, output_path: Optional[str] = None) -> str:
        """
        Create a backup of the database

        Args:
            output_path: Output file path (default: auto-generated)

        Returns:
            Path to backup file
        """
        if not output_path:
            timestamp = date.today().strftime('%Y%m%d')
            output_path = f"data/backups/bond_lab_{timestamp}.duckdb"

        output_path = Path(output_path)

        # Create backup directory if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy database file
        shutil.copy2(self.db_path, output_path)

        logger.info(f"Database backed up to {output_path}")
        return str(output_path)

    def restore(self, backup_path: str, require_confirmation: bool = True):
        """
        Restore database from backup

        Args:
            backup_path: Path to backup file
            require_confirmation: If True, check env flag

        Raises:
            RuntimeError: If confirmation not given
        """
        if require_confirmation:
            import os
            if os.getenv('ALLOW_RESTORE', 'false').lower() != 'true':
                raise RuntimeError(
                    "Restore operation requires ALLOW_RESTORE=true environment variable. "
                    "This is a safety measure to prevent accidental data loss."
                )

        backup_path = Path(backup_path)

        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        # Verify backup is valid
        self.verify_backup(backup_path)

        # Create a backup of current database before restore
        current_backup = f"{self.db_path}.pre_restore"
        shutil.copy2(self.db_path, current_backup)
        logger.info(f"Current database backed up to {current_backup}")

        # Restore from backup
        shutil.copy2(backup_path, self.db_path)

        logger.info(f"Database restored from {backup_path}")

    def export_dataset(
        self,
        table_name: str,
        start_date: str,
        end_date: str,
        output_path: str,
        format: str = 'csv'
    ):
        """
        Export dataset to CSV file

        Args:
            table_name: Table name to export
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            output_path: Output CSV file path
            format: Export format (only 'csv' supported)
        """
        import duckdb

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        con = duckdb.connect(str(self.db_path))

        try:
            # Export to CSV
            sql = f"COPY (SELECT * FROM {table_name} WHERE date >= '{start_date}' AND date <= '{end_date}') TO '{output_path}' (HEADER, DELIMITER ',')"
            con.execute(sql)

            logger.info(f"Exported {table_name} ({start_date} to {end_date}) to {output_path}")

        finally:
            con.close()

    def import_dataset(
        self,
        table_name: str,
        input_path: str,
        format: str = 'csv'
    ):
        """
        Import dataset from CSV file

        Args:
            table_name: Target table name
            input_path: Input CSV file path
            format: Import format (only 'csv' supported)
        """
        import duckdb

        input_path = Path(input_path)

        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        con = duckdb.connect(str(self.db_path))

        try:
            # Import from CSV
            sql = f"INSERT INTO {table_name} SELECT * FROM read_csv_auto('{input_path}')"
            con.execute(sql)

            logger.info(f"Imported data into {table_name} from {input_path}")

        finally:
            con.close()

    def verify_backup(self, backup_path: str) -> dict:
        """
        Verify backup file integrity

        Args:
            backup_path: Path to backup file

        Returns:
            Dictionary with verification results
        """
        import duckdb

        backup_path = Path(backup_path)

        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        con = duckdb.connect(str(backup_path))

        try:
            # Check if database is readable
            tables_result = con.execute("SHOW TABLES").fetchall()
            tables = [row[0] for row in tables_result]

            # Check expected tables exist (informational for VN Bond Lab backups)
            required_tables = [
                'gov_yield_curve',
                'interbank_rates',
                'transmission_daily_metrics',
                'bondy_stress_daily',
                'dq_runs',
                'dq_results'
            ]

            missing_tables = [t for t in required_tables if t not in tables]

            verification = {
                'backup_file': str(backup_path),
                'readable': True,
                'total_tables': len(tables),
                'tables': tables,
                'missing_tables': missing_tables,
                # A backup is considered valid if it's readable and has tables;
                # missing VN Bond Lab tables are reported but don't invalidate
                # arbitrary DuckDB backups.
                'valid': len(tables) > 0
            }

            return verification

        except Exception as e:
            logger.error(f"Backup verification failed: {e}")
            return {
                'backup_file': str(backup_path),
                'readable': False,
                'error': str(e),
                'valid': False
            }
        finally:
            con.close()

    def list_backups(self, backup_dir: str = "data/backups") -> List[dict]:
        """
        List all backups in directory

        Args:
            backup_dir: Directory containing backups

        Returns:
            List of backup info dictionaries
        """
        backup_path = Path(backup_dir)

        if not backup_path.exists():
            return []

        backups = []
        for file in backup_path.glob("bond_lab_*.duckdb"):
            stat = file.stat()
            backups.append({
                'filename': file.name,
                'path': str(file),
                'size_mb': round(stat.st_size / (1024 * 1024), 2),
                'created': stat.st_ctime
            })

        # Sort by creation time (newest first)
        backups.sort(key=lambda x: x['created'], reverse=True)

        return backups
