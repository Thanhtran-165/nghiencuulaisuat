"""
Observability and Metrics Module

Provides Prometheus-style metrics for monitoring and SLO tracking.
"""
import logging
import time
import hashlib
from typing import Dict, Any, Optional
from datetime import datetime
from collections import defaultdict

from app.config import settings

logger = logging.getLogger(__name__)


class MetricsRegistry:
    """Registry for Prometheus-style metrics"""

    def __init__(self):
        self._counters = defaultdict(int)
        self._gauges = {}
        self._histograms = defaultdict(list)

    def increment_counter(self, name: str, labels: Dict[str, str] = None, value: int = 1):
        """Increment a counter metric"""
        label_key = self._label_key(name, labels)
        self._counters[label_key] += value

    def set_gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        """Set a gauge metric"""
        label_key = self._label_key(name, labels)
        self._gauges[label_key] = value

    def observe_histogram(self, name: str, value: float, labels: Dict[str, str] = None):
        """Observe a value for a histogram"""
        label_key = self._label_key(name, labels)
        self._histograms[label_key].append(value)

    def _label_key(self, name: str, labels: Dict[str, str] = None) -> str:
        """Generate a key for labeled metrics"""
        if not labels:
            return name

        label_str = ','.join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def format_prometheus(self) -> str:
        """Export metrics in Prometheus exposition format"""
        lines = [
            "# TYPE vn_bond_lab_up gauge",
            "vn_bond_lab_up 1",
        ]

        # Counters
        for key, value in sorted(self._counters.items()):
            lines.append(f"# TYPE {key.split('{')[0]} counter")
            lines.append(f"{key} {value}")

        # Gauges
        for key, value in sorted(self._gauges.items()):
            lines.append(f"# TYPE {key.split('{')[0]} gauge")
            lines.append(f"{key} {value}")

        # Histograms
        for key, values in sorted(self._histograms.items()):
            if values:
                lines.append(f"# TYPE {key.split('{')[0]} histogram")
                count = len(values)
                total = sum(values)
                lines.append(f"{key}_count {count}")
                lines.append(f"{key}_sum {total}")

        return '\n'.join(lines)


# Global metrics registry
metrics_registry = MetricsRegistry()


def track_provider_latency(provider: str):
    """Context manager to track provider fetch latency"""
    class LatencyTracker:
        def __init__(self, provider_name: str):
            self.provider = provider_name

        def __enter__(self):
            self.start = time.time()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            duration = time.time() - self.start
            status = "error" if exc_type else "success"

            metrics_registry.observe_histogram(
                "provider_fetch_latency_seconds",
                duration,
                labels={"provider": self.provider, "status": status}
            )

            if exc_type is None:
                metrics_registry.increment_counter(
                    "ingest_runs_total",
                    labels={"provider": self.provider, "status": "success"}
                )
            else:
                metrics_registry.increment_counter(
                    "ingest_runs_total",
                    labels={"provider": self.provider, "status": "error"}
                )

    return LatencyTracker(provider)


def update_dq_metrics(severity: str, dataset: str, passed: bool):
    """Update DQ metrics"""
    metrics_registry.increment_counter(
        "dq_results_total",
        labels={"severity": severity, "dataset": dataset, "passed": str(passed).lower()}
    )


def update_notification_metrics(status: str, channel_type: str):
    """Update notification metrics"""
    metrics_registry.increment_counter(
        "notifications_total",
        labels={"status": status, "channel_type": channel_type}
    )


def update_provider_success_timestamp(provider: str, dataset: str):
    """Update last success timestamp for provider/dataset"""
    metrics_registry.set_gauge(
        "last_success_timestamp",
        time.time(),
        labels={"provider": provider, "dataset": dataset}
    )


def get_health_status() -> Dict[str, Any]:
    """Get quick health status (no DB query)"""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat()
    }


def get_readiness_status(db_manager) -> Dict[str, Any]:
    """Get detailed readiness status (includes DB checks)"""
    try:
        now = datetime.utcnow().isoformat()

        if db_manager is None:
            return {
                "status": "not_ready",
                "database": {"status": "missing"},
                "reason": "database_not_configured",
                "timestamp": now,
            }

        # Check DB connectivity
        if not getattr(db_manager, "con", None):
            return {
                "status": "not_ready",
                "database": {"status": "not_connected"},
                "reason": "database_not_connected",
                "timestamp": now,
            }

        # Check schema presence
        tables_result = db_manager.con.execute("SHOW TABLES").fetchall()
        table_names = [row[0] for row in tables_result]

        required_tables = ['gov_yield_curve', 'interbank_rates', 'transmission_daily_metrics', 'dq_runs']
        missing_tables = [t for t in required_tables if t not in table_names]

        if missing_tables:
            return {
                "status": "not_ready",
                "reason": "missing_tables",
                "missing_tables": missing_tables
            }

        # Get last ingest run
        try:
            ingest_result = db_manager.con.execute("""
                SELECT run_id, status, start_date, end_date, started_at
                FROM ingest_runs
                ORDER BY started_at DESC
                LIMIT 1
            """).fetchone()

            last_ingest = {
                'run_id': ingest_result[0],
                'status': ingest_result[1],
                'start_date': str(ingest_result[2]),
                'end_date': str(ingest_result[3]),
                'started_at': str(ingest_result[4])
            } if ingest_result else None
        except Exception:
            last_ingest = None

        # Get last DQ status
        try:
            dq_result = db_manager.con.execute("""
                SELECT run_id, status, target_date, run_at
                FROM dq_runs
                ORDER BY run_at DESC
                LIMIT 1
            """).fetchone()

            last_dq = {
                'run_id': dq_result[0],
                'status': dq_result[1],
                'target_date': str(dq_result[2]),
                'run_at': str(dq_result[3])
            } if dq_result else None
        except Exception:
            last_dq = None

        # Get last compute dates
        last_compute_date = None
        try:
            trans_result = db_manager.con.execute("""
                SELECT MAX(date) as last_date
                FROM transmission_daily_metrics
                WHERE metric_name = 'transmission_score'
            """).fetchone()

            stress_result = db_manager.con.execute("""
                SELECT MAX(date) as last_date
                FROM bondy_stress_daily
            """).fetchone()

            last_compute_date = {
                'transmission': str(trans_result[0]) if trans_result and trans_result[0] else None,
                'stress': str(stress_result[0]) if stress_result and stress_result[0] else None
            }
        except Exception:
            pass

        return {
            "status": "ok",
            "database": {"status": "ok"},
            "tables": len(table_names),
            "last_ingest_run": last_ingest,
            "last_dq_status": last_dq,
            "last_compute_date": last_compute_date,
            "demo_mode_enabled": settings.demo_mode,
            "timestamp": now,
        }

    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {
            "status": "not_ready",
            "database": {"status": "error"},
            "reason": "readiness_check_failed",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }
