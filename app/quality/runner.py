"""
Data Quality Runner

Executes DQ rules for a date and dataset, saves results to database.
Implements gate policy (ERROR blocks compute, WARN allows with banner).
"""
import logging
from datetime import date
from typing import Dict, Any, List, Optional
from .rules import get_rules_for_dataset, get_all_datasets

logger = logging.getLogger(__name__)


class DataQualityRunner:
    """Runs data quality checks and implements gate policy"""

    def __init__(self, db_manager):
        """
        Initialize DQ runner

        Args:
            db_manager: Database manager instance
        """
        self.db = db_manager

    def run_dq_for_date(
        self,
        target_date: date,
        datasets: Optional[List[str]] = None,
        override_block: bool = False
    ) -> Dict[str, Any]:
        """
        Run all DQ rules for target date

        Args:
            target_date: Date to run checks for
            datasets: List of dataset IDs to check (None = all)
            override_block: If True, ERROR results won't block compute

        Returns:
            Dictionary with run results:
            {
                'run_id': int,
                'status': 'PASS' | 'WARN' | 'FAIL',
                'should_block': bool,
                'summary': {...}
            }
        """
        if datasets is None:
            datasets = get_all_datasets()

        logger.info(f"Running DQ checks for {target_date} across {len(datasets)} datasets")

        # Create DQ run record
        run_id = self._create_dq_run(target_date)

        all_results = []
        error_count = 0
        warn_count = 0
        info_count = 0

        # Run rules for each dataset
        for dataset_id in datasets:
            rules = get_rules_for_dataset(dataset_id)

            for rule in rules:
                try:
                    passed, severity, message, details = rule.check(self.db, target_date)

                    # Save result to database
                    result_id = self._save_dq_result(
                        run_id=run_id,
                        target_date=target_date,
                        dataset_id=dataset_id,
                        rule_code=rule.rule_code,
                        severity=severity,
                        passed=passed,
                        message=message,
                        details=details
                    )

                    all_results.append({
                        'dataset_id': dataset_id,
                        'rule_code': rule.rule_code,
                        'severity': severity,
                        'passed': passed,
                        'message': message
                    })

                    # Count by severity
                    if severity == 'ERROR':
                        error_count += 1
                    elif severity == 'WARN':
                        warn_count += 1
                    else:
                        info_count += 1

                except Exception as e:
                    logger.error(f"Error running rule {rule.rule_code}: {e}")
                    # Save error result
                    self._save_dq_result(
                        run_id=run_id,
                        target_date=target_date,
                        dataset_id=dataset_id,
                        rule_code=rule.rule_code,
                        severity='ERROR',
                        passed=False,
                        message=f"Rule execution failed: {str(e)}",
                        details={'error': str(e)}
                    )
                    error_count += 1

        # Determine overall status
        if error_count > 0:
            overall_status = 'FAIL'
            should_block = not override_block
        elif warn_count > 0:
            overall_status = 'WARN'
            should_block = False
        else:
            overall_status = 'PASS'
            should_block = False

        # Update run record with final status
        self._update_dq_run(run_id, overall_status, {
            'error_count': error_count,
            'warn_count': warn_count,
            'info_count': info_count,
            'total_rules_checked': len(all_results),
            'override_block': override_block
        })

        logger.info(f"DQ run complete: {overall_status} (errors: {error_count}, warnings: {warn_count})")

        return {
            'run_id': run_id,
            'status': overall_status,
            'should_block': should_block,
            'summary': {
                'error_count': error_count,
                'warn_count': warn_count,
                'info_count': info_count,
                'total_rules_checked': len(all_results)
            },
            'results': all_results
        }

    def get_dq_status_for_date(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        Get DQ status for a specific date

        Returns:
            DQ run summary or None if no run exists
        """
        try:
            sql = """
            SELECT id, run_at, target_date, status, summary_json
            FROM dq_runs
            WHERE target_date = ?
            ORDER BY run_at DESC
            LIMIT 1
            """

            result = self.db.con.execute(sql, [str(target_date)]).fetchone()

            if not result:
                return None

            import json
            return {
                'run_id': result[0],
                'run_at': str(result[1]),
                'target_date': str(result[2]),
                'status': result[3],
                'summary': json.loads(result[4]) if result[4] else {}
            }

        except Exception as e:
            logger.error(f"Error getting DQ status: {e}")
            return None

    def get_dq_results(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        dataset_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get DQ results with filters

        Args:
            start_date: Filter results from this date
            end_date: Filter results until this date
            dataset_id: Filter by dataset
            severity: Filter by severity (INFO/WARN/ERROR)
            limit: Max results to return

        Returns:
            List of DQ result dictionaries
        """
        try:
            sql = """
            SELECT r.id, r.target_date, r.dataset_id, r.rule_code,
                   r.severity, r.passed, r.message, r.details_json,
                   r.created_at
            FROM dq_results r
            WHERE 1=1
            """

            params = []

            if start_date:
                sql += " AND r.target_date >= ?"
                params.append(str(start_date))

            if end_date:
                sql += " AND r.target_date <= ?"
                params.append(str(end_date))

            if dataset_id:
                sql += " AND r.dataset_id = ?"
                params.append(dataset_id)

            if severity:
                sql += " AND r.severity = ?"
                params.append(severity)

            sql += " ORDER BY r.created_at DESC LIMIT ?"
            params.append(limit)

            results = self.db.con.execute(sql, params).fetchall()

            import json
            output = []
            for row in results:
                output.append({
                    'id': row[0],
                    'target_date': str(row[1]),
                    'dataset_id': row[2],
                    'rule_code': row[3],
                    'severity': row[4],
                    'passed': bool(row[5]),
                    'message': row[6],
                    'details': json.loads(row[7]) if row[7] else {},
                    'created_at': str(row[8])
                })

            return output

        except Exception as e:
            logger.error(f"Error getting DQ results: {e}")
            return []

    def _create_dq_run(self, target_date: date) -> int:
        """Create a new DQ run record and return its ID"""
        try:
            run_id = self.db.con.execute("SELECT nextval('dq_runs_id_seq')").fetchone()[0]
            sql = """
            INSERT INTO dq_runs (id, target_date, status, summary_json)
            VALUES (?, ?, 'IN_PROGRESS', 'null')
            """
            self.db.con.execute(sql, [run_id, str(target_date)])
            return int(run_id)

        except Exception as e:
            logger.error(f"Error creating DQ run: {e}")
            raise

    def _update_dq_run(self, run_id: int, status: str, summary: Dict[str, Any]):
        """Update DQ run with final status"""
        try:
            import json
            sql = """
            UPDATE dq_runs
            SET status = ?,
                summary_json = ?
            WHERE id = ?
            """

            self.db.con.execute(sql, [status, json.dumps(summary), run_id])

        except Exception as e:
            logger.error(f"Error updating DQ run: {e}")

    def _save_dq_result(
        self,
        run_id: int,
        target_date: date,
        dataset_id: str,
        rule_code: str,
        severity: str,
        passed: bool,
        message: str,
        details: Dict[str, Any]
    ) -> int:
        """Save a DQ result and return its ID"""
        try:
            import json
            result_id = self.db.con.execute("SELECT nextval('dq_results_id_seq')").fetchone()[0]
            sql = """
            INSERT INTO dq_results (id, target_date, dataset_id, rule_code, severity, passed, message, details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (target_date, dataset_id, rule_code)
            DO UPDATE SET
                severity = EXCLUDED.severity,
                passed = EXCLUDED.passed,
                message = EXCLUDED.message,
                details_json = EXCLUDED.details_json,
                created_at = get_current_timestamp()
            RETURNING id
            """

            result = self.db.con.execute(sql, [
                result_id,
                str(target_date),
                dataset_id,
                rule_code,
                severity,
                passed,
                message,
                json.dumps(details)
            ]).fetchone()

            return result[0]

        except Exception as e:
            logger.error(f"Error saving DQ result: {e}")
            raise

    def should_block_compute(self, target_date: date) -> bool:
        """
        Check if analytics compute should be blocked for this date

        Args:
            target_date: Date to check

        Returns:
            True if ERROR-severity failures exist and not overridden
        """
        dq_status = self.get_dq_status_for_date(target_date)

        if not dq_status:
            # No DQ run - assume OK (backward compatibility)
            return False

        if dq_status['status'] == 'FAIL':
            # Check if override was set
            summary = dq_status.get('summary', {})
            return not summary.get('override_block', False)

        return False

    def get_dq_banner_message(self, target_date: date) -> Optional[str]:
        """
        Get banner message for snapshot/report if DQ issues exist

        Returns:
            Banner message or None
        """
        dq_status = self.get_dq_status_for_date(target_date)

        if not dq_status:
            return None

        status = dq_status['status']
        summary = dq_status.get('summary', {})

        if status == 'FAIL':
            error_count = summary.get('error_count', 0)
            return f"⚠️ DATA QUALITY FAILED: {error_count} error(s) detected. Analytics may be unreliable."
        elif status == 'WARN':
            warn_count = summary.get('warn_count', 0)
            return f"⚠️ DATA QUALITY WARNING: {warn_count} warning(s) detected. Review recommended."

        return None
