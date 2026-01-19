"""
Data Quality CLI Entry Point

Usage:
    python -m app.quality run --date YYYY-MM-DD
    python -m app.quality run-range --start YYYY-MM-DD --end YYYY-MM-DD
"""
import argparse
import logging
import sys
from datetime import date
from app.db.schema import DatabaseManager
from app.quality import DataQualityRunner

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cmd_run(args):
    """Run DQ checks for a single date"""
    db = DatabaseManager(args.db)
    db.connect()

    runner = DataQualityRunner(db)

    target_date = date.fromisoformat(args.date)

    result = runner.run_dq_for_date(
        target_date=target_date,
        datasets=args.datasets.split(',') if args.datasets else None,
        override_block=args.override
    )

    print(f"\n{'='*60}")
    print(f"Data Quality Run Results for {target_date}")
    print(f"{'='*60}")
    print(f"Status: {result['status']}")
    print(f"Should Block Compute: {result['should_block']}")
    print(f"\nSummary:")
    for key, value in result['summary'].items():
        print(f"  {key}: {value}")

    if result['status'] != 'PASS':
        print(f"\n{'='*60}")
        print("Failed Checks:")
        for r in result['results']:
            if not r['passed']:
                print(f"  [{r['severity']}] {r['dataset_id']}.{r['rule_code']}")
                print(f"    {r['message']}")

    print(f"\nRun ID: {result['run_id']}")

    # Exit with error code if failed
    if result['status'] == 'FAIL' and not args.override:
        sys.exit(1)


def cmd_run_range(args):
    """Run DQ checks for a date range"""
    db = DatabaseManager(args.db)
    db.connect()

    runner = DataQualityRunner(db)

    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)

    print(f"Running DQ checks from {start_date} to {end_date}")

    current_date = start_date
    fail_count = 0
    warn_count = 0
    pass_count = 0

    while current_date <= end_date:
        result = runner.run_dq_for_date(
            target_date=current_date,
            datasets=args.datasets.split(',') if args.datasets else None,
            override_block=args.override
        )

        status_symbol = {
            'PASS': '✓',
            'WARN': '⚠',
            'FAIL': '✗'
        }[result['status']]

        print(f"{current_date} {status_symbol} {result['status']}")

        if result['status'] == 'FAIL':
            fail_count += 1
        elif result['status'] == 'WARN':
            warn_count += 1
        else:
            pass_count += 1

        current_date += timedelta(days=1)

    print(f"\n{'='*60}")
    print(f"Range Summary:")
    print(f"  PASS: {pass_count}")
    print(f"  WARN: {warn_count}")
    print(f"  FAIL: {fail_count}")
    print(f"{'='*60}")

    if fail_count > 0 and not args.override:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='Data Quality CLI for VN Bond Lab')
    parser.add_argument('--db', default='data/bond_lab.db', help='Database path')

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Run command
    run_parser = subparsers.add_parser('run', help='Run DQ for a single date')
    run_parser.add_argument('--date', required=True, help='Target date (YYYY-MM-DD)')
    run_parser.add_argument('--datasets', help='Comma-separated list of datasets (default: all)')
    run_parser.add_argument('--override', action='store_true', help='Override ERROR blocks')
    run_parser.set_defaults(func=cmd_run)

    # Run-range command
    range_parser = subparsers.add_parser('run-range', help='Run DQ for date range')
    range_parser.add_argument('--start', required=True, help='Start date (YYYY-MM-DD)')
    range_parser.add_argument('--end', required=True, help='End date (YYYY-MM-DD)')
    range_parser.add_argument('--datasets', help='Comma-separated list of datasets (default: all)')
    range_parser.add_argument('--override', action='store_true', help='Override ERROR blocks')
    range_parser.set_defaults(func=cmd_run_range)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    from datetime import timedelta
    main()
