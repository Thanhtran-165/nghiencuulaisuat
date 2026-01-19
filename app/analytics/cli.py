"""
CLI for analytics operations
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.db.schema import DatabaseManager
from app.analytics.transmission import TransmissionAnalytics

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/analytics.log')
    ]
)
logger = logging.getLogger(__name__)


def main():
    """CLI entry point for analytics operations"""
    import argparse

    parser = argparse.ArgumentParser(description='VN Bond Lab - Analytics CLI')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Compute command
    compute_parser = subparsers.add_parser('compute', help='Compute transmission metrics for a specific date')
    compute_parser.add_argument(
        '--date',
        required=True,
        help='Target date (YYYY-MM-DD)'
    )

    # Compute-range command
    range_parser = subparsers.add_parser('compute-range', help='Compute transmission metrics for a date range')
    range_parser.add_argument(
        '--start',
        required=True,
        help='Start date (YYYY-MM-DD)'
    )
    range_parser.add_argument(
        '--end',
        required=True,
        help='End date (YYYY-MM-DD)'
    )

    # Stress compute command
    stress_parser = subparsers.add_parser('stress', help='Compute BondY stress index for a specific date')
    stress_parser.add_argument(
        '--date',
        required=True,
        help='Target date (YYYY-MM-DD)'
    )

    # Stress-range command
    stress_range_parser = subparsers.add_parser('stress-range', help='Compute BondY stress index for a date range')
    stress_range_parser.add_argument(
        '--start',
        required=True,
        help='Start date (YYYY-MM-DD)'
    )
    stress_range_parser.add_argument(
        '--end',
        required=True,
        help='End date (YYYY-MM-DD)'
    )

    # Transmission score distribution summary
    score_summary_parser = subparsers.add_parser(
        'score-summary',
        help='Summarize computed transmission_score distribution over a date range'
    )
    score_summary_parser.add_argument(
        '--start',
        required=True,
        help='Start date (YYYY-MM-DD)'
    )
    score_summary_parser.add_argument(
        '--end',
        required=True,
        help='End date (YYYY-MM-DD)'
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Ensure logs directory exists
    Path('logs').mkdir(exist_ok=True)

    # Initialize database
    db_manager = DatabaseManager(settings.db_path)
    read_only = args.command in {"score-summary"}
    db_manager.connect(read_only=read_only)
    if not read_only:
        db_manager.initialize_schema()

    try:
        if args.command == 'compute':
            compute_metrics_for_date(db_manager, args.date)
        elif args.command == 'compute-range':
            compute_metrics_for_range(db_manager, args.start, args.end)
        elif args.command == 'stress':
            compute_stress_for_date(db_manager, args.date)
        elif args.command == 'stress-range':
            compute_stress_for_range(db_manager, args.start, args.end)
        elif args.command == 'score-summary':
            summarize_transmission_score(db_manager, args.start, args.end)
        else:
            parser.print_help()
            sys.exit(1)

    finally:
        db_manager.close()


def compute_metrics_for_date(db_manager: DatabaseManager, target_date: str):
    """
    Compute transmission metrics for a specific date

    Args:
        db_manager: Database manager instance
        target_date: Target date string (YYYY-MM-DD)
    """
    try:
        target = datetime.strptime(target_date, '%Y-%m-%d').date()
        logger.info(f"Computing transmission metrics for {target_date}")

        analytics = TransmissionAnalytics(db_manager)
        metrics, alerts = analytics.compute_daily_metrics(target)

        # Insert metrics
        db_manager.insert_transmission_metrics(target_date, metrics)

        # Insert alerts
        if alerts:
            db_manager.insert_transmission_alerts(target_date, alerts)

        logger.info(f"✓ Computed {len(metrics)} metrics for {target_date}")
        logger.info(f"✓ Generated {len(alerts)} alerts for {target_date}")

        # Print summary
        score = metrics.get('transmission_score')
        bucket = metrics.get('regime_bucket')
        if score and bucket:
            logger.info(f"  Transmission Score: {score:.1f}/100")
            logger.info(f"  Regime Bucket: {bucket}")

        if alerts:
            logger.info("  Alerts generated:")
            for alert in alerts:
                logger.info(f"    - [{alert['severity']}] {alert['alert_type']}: {alert['message']}")

    except Exception as e:
        logger.error(f"Failed to compute metrics for {target_date}: {e}")
        sys.exit(1)


def compute_metrics_for_range(
    db_manager: DatabaseManager,
    start_date: str,
    end_date: str
):
    """
    Compute transmission metrics for a date range

    Args:
        db_manager: Database manager instance
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
    """
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()

        if start > end:
            logger.error("Start date must be before or equal to end date")
            sys.exit(1)

        logger.info(f"Computing transmission metrics from {start_date} to {end_date}")

        analytics = TransmissionAnalytics(db_manager)
        current = start

        total_metrics = 0
        total_alerts = 0
        failed_dates = []

        while current <= end:
            try:
                logger.info(f"Processing {current}...")

                metrics, alerts = analytics.compute_daily_metrics(current)

                # Insert metrics
                db_manager.insert_transmission_metrics(current.strftime('%Y-%m-%d'), metrics)

                # Insert alerts
                if alerts:
                    db_manager.insert_transmission_alerts(current.strftime('%Y-%m-%d'), alerts)

                total_metrics += len(metrics)
                total_alerts += len(alerts)

                score = metrics.get('transmission_score')
                bucket = metrics.get('regime_bucket')
                if score and bucket:
                    logger.info(f"  ✓ Score: {score:.1f}/100, Bucket: {bucket}, Alerts: {len(alerts)}")

            except Exception as e:
                logger.warning(f"  ✗ Failed: {e}")
                failed_dates.append((current, str(e)))

            current += timedelta(days=1)

        # Print summary
        logger.info("=" * 60)
        logger.info("COMPUTE-RANGE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Date range: {start_date} to {end_date}")
        logger.info(f"Total dates processed: {(end - start).days + 1}")
        logger.info(f"Successful: {(end - start).days + 1 - len(failed_dates)}")
        logger.info(f"Failed: {len(failed_dates)}")
        logger.info(f"Total metrics computed: {total_metrics}")
        logger.info(f"Total alerts generated: {total_alerts}")

        if failed_dates:
            logger.info("")
            logger.info("Failed dates:")
            for fail_date, error in failed_dates:
                logger.info(f"  {fail_date}: {error}")

        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Failed to compute metrics for range: {e}")
        sys.exit(1)


def compute_stress_for_date(db_manager: DatabaseManager, target_date: str):
    """
    Compute BondY stress index for a specific date

    Args:
        db_manager: Database manager instance
        target_date: Target date string (YYYY-MM-DD)
    """
    try:
        from app.analytics.stress_model import BondYStressModel
        import json

        target = datetime.strptime(target_date, '%Y-%m-%d').date()
        logger.info(f"Computing BondY stress index for {target_date}")

        stress_model = BondYStressModel(db_manager)
        stress_index, regime_bucket, components = stress_model.compute_stress_index(target)

        # Insert stress record
        driver_json = json.dumps(components.get('drivers', []))
        db_manager.insert_bondy_stress(
            target_date,
            stress_index,
            regime_bucket,
            driver_json
        )

        logger.info(f"✓ Computed BondY stress: {stress_index}/100, bucket: {regime_bucket}")

        # Compute global comparators if available
        try:
            comparators = stress_model.compute_global_comparators(target)

            if comparators.get('global_available'):
                logger.info("✓ Global comparators computed")

                # Store global alerts
                if comparators.get('alerts'):
                    for alert in comparators['alerts']:
                        logger.info(f"  - [{alert['severity']}] {alert['alert_type']}: {alert['message']}")
        except Exception as e:
            logger.warning(f"  ✗ Global comparators failed: {e}")

    except Exception as e:
        logger.error(f"Failed to compute stress for {target_date}: {e}")
        sys.exit(1)


def summarize_transmission_score(db_manager: DatabaseManager, start_date: str, end_date: str):
    """
    Summarize transmission_score distribution for calibration / sanity checks.
    """
    try:
        rows = db_manager.con.execute(
            """
            SELECT metric_value
            FROM transmission_daily_metrics
            WHERE metric_name = 'transmission_score'
              AND metric_value IS NOT NULL
              AND date >= ? AND date <= ?
            ORDER BY date
            """,
            [start_date, end_date],
        ).fetchall()

        values = [float(r[0]) for r in rows if r and r[0] is not None]
        if not values:
            logger.info("No transmission_score values found in the requested range.")
            return

        values_sorted = sorted(values)

        def quantile(q: float) -> float:
            if q <= 0:
                return values_sorted[0]
            if q >= 1:
                return values_sorted[-1]
            pos = (len(values_sorted) - 1) * q
            lo = int(pos)
            hi = min(lo + 1, len(values_sorted) - 1)
            w = pos - lo
            return values_sorted[lo] * (1 - w) + values_sorted[hi] * w

        logger.info("=" * 60)
        logger.info("TRANSMISSION SCORE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Range: {start_date} to {end_date}")
        logger.info(f"N: {len(values_sorted)}")
        logger.info(f"Min/Max: {values_sorted[0]:.2f} / {values_sorted[-1]:.2f}")
        logger.info(
            "Quantiles: "
            f"p20={quantile(0.20):.2f}, "
            f"p40={quantile(0.40):.2f}, "
            f"p50={quantile(0.50):.2f}, "
            f"p60={quantile(0.60):.2f}, "
            f"p80={quantile(0.80):.2f}"
        )
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"Failed to summarize transmission score: {e}")
        sys.exit(1)


def compute_stress_for_range(
    db_manager: DatabaseManager,
    start_date: str,
    end_date: str
):
    """
    Compute BondY stress index for a date range

    Args:
        db_manager: Database manager instance
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
    """
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()

        if start > end:
            logger.error("Start date must be before or equal to end date")
            sys.exit(1)

        logger.info(f"Computing BondY stress index from {start_date} to {end_date}")

        stress_model = BondYStressModel(db_manager)
        current = start

        total_computed = 0
        failed_dates = []

        while current <= end:
            try:
                logger.info(f"Processing {current}...")

                stress_index, regime_bucket, components = stress_model.compute_stress_index(current)

                # Insert stress record
                import json
                driver_json = json.dumps(components.get('drivers', []))
                db_manager.insert_bondy_stress(
                    current.strftime('%Y-%m-%d'),
                    stress_index,
                    regime_bucket,
                    driver_json
                )

                total_computed += 1
                logger.info(f"  ✓ Stress: {stress_index}/100, bucket: {regime_bucket}")

            except Exception as e:
                logger.warning(f"  ✗ Failed: {e}")
                failed_dates.append((current, str(e)))

            current += timedelta(days=1)

        # Print summary
        logger.info("=" * 60)
        logger.info("STRESS-RANGE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Date range: {start_date} to {end_date}")
        logger.info(f"Total dates processed: {(end - start).days + 1}")
        logger.info(f"Successful: {(end - start).days + 1 - len(failed_dates)}")
        logger.info(f"Failed: {len(failed_dates)}")
        logger.info(f"Total stress indices computed: {total_computed}")

        if failed_dates:
            logger.info("")
            logger.info("Failed dates:")
            for fail_date, error in failed_dates:
                logger.info(f"  {fail_date}: {error}")

        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Failed to compute stress for range: {e}")
        sys.exit(1)


from datetime import timedelta


if __name__ == '__main__':
    main()
