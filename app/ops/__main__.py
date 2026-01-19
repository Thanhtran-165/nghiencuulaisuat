"""
Ops CLI Entry Point

Usage:
    python -m app.ops backup --out data/backups/bond_lab_YYYYMMDD.duckdb
    python -m app.ops restore --in <file> --yes
    python -m app.ops export --dataset <table> --start YYYY-MM-DD --end YYYY-MM-DD --out <csv>
    python -m app.ops import-interbank --in <csv> --tenors 3M --source <name>
    python -m app.ops verify-backup --in <file>
    python -m app.ops list-backups
    python -m app.ops seed-demo --days 180
"""
import argparse
import logging
import sys
import json
from app.ops.manager import OpsManager
from app.ops.import_interbank import parse_interbank_csv
from app.db.schema import DatabaseManager
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cmd_backup(args):
    """Create a database backup"""
    ops = OpsManager(args.db)

    backup_path = ops.backup(output_path=args.out)

    print(f"✓ Backup created: {backup_path}")

    # Verify backup
    verification = ops.verify_backup(backup_path)
    if verification['valid']:
        print(f"✓ Backup verified successfully")
        print(f"  Tables: {verification['total_tables']}")
    else:
        print(f"⚠ Backup verification failed")
        print(f"  Missing tables: {verification.get('missing_tables', [])}")
        sys.exit(1)


def cmd_restore(args):
    """Restore database from backup"""
    ops = OpsManager(args.db)

    try:
        ops.restore(args.inp, require_confirmation=not args.yes)
        print(f"✓ Database restored from {args.inp}")
        print(f"⚠ Make sure to restart the application")

    except RuntimeError as e:
        print(f"✗ Restore failed: {e}")
        print("\nSafety: To enable restore operations, set:")
        print("  export ALLOW_RESTORE=true")
        sys.exit(1)


def cmd_export(args):
    """Export dataset to CSV"""
    ops = OpsManager(args.db)

    ops.export_dataset(
        table_name=args.dataset,
        start_date=args.start,
        end_date=args.end,
        output_path=args.out
    )

    print(f"✓ Exported {args.dataset} to {args.out}")

def cmd_import_interbank(args):
    """Import interbank rates from CSV (long or wide format)"""
    tenors = None
    if args.tenors:
        tenors = [t.strip() for t in args.tenors.split(",") if t.strip()]

    parsed = parse_interbank_csv(
        args.inp,
        default_source=args.source,
        only_tenors=tenors,
    )

    db = DatabaseManager(args.db)
    db.connect()
    try:
        db.initialize_schema()
        inserted = db.insert_interbank_rates(parsed.records)
    finally:
        db.close()

    print(f"✓ Imported {inserted} interbank records from {args.inp}")
    if parsed.skipped_rows:
        print(f"  Skipped rows (invalid date/rate): {parsed.skipped_rows}")


def cmd_verify_backup(args):
    """Verify backup file"""
    ops = OpsManager(args.db)

    verification = ops.verify_backup(args.inp)

    print(f"\nBackup Verification: {verification['backup_file']}")
    print(f"  Readable: {'Yes' if verification['readable'] else 'No'}")

    if verification['readable']:
        print(f"  Total Tables: {verification['total_tables']}")
        print(f"  Valid: {'Yes' if verification['valid'] else 'No'}")

        if verification.get('missing_tables'):
            print(f"  Missing Tables: {verification['missing_tables']}")

        if verification['valid']:
            print(f"\n✓ Backup is valid")
            sys.exit(0)
        else:
            print(f"\n⚠ Backup has issues")
            sys.exit(1)
    else:
        print(f"  Error: {verification.get('error', 'Unknown')}")
        print(f"\n✗ Backup is invalid")
        sys.exit(1)


def cmd_list_backups(args):
    """List all backups"""
    ops = OpsManager(args.db)

    backups = ops.list_backups(args.dir)

    if not backups:
        print(f"No backups found in {args.dir}")
        return

    print(f"\nBackups in {args.dir}:")
    print(f"{'Filename':<40} {'Size (MB)':<12} {'Created'}")
    print("=" * 80)

    for backup in backups:
        from datetime import datetime
        created = datetime.fromtimestamp(backup['created']).strftime('%Y-%m-%d %H:%M:%S')
        print(f"{backup['filename']:<40} {backup['size_mb']:<12.2f} {created}")


def cmd_seed_demo(args):
    """Seed demo data for demonstration"""
    from app.db.schema import DatabaseManager
    from datetime import date, timedelta
    import random

    print(f"Seeding demo data for {args.days} days...")

    # Initialize database
    db = DatabaseManager(args.db)
    db.connect()
    db.initialize_schema()

    # Generate dates
    end_date = date.today()
    start_date = end_date - timedelta(days=args.days)
    dates = []
    current = start_date
    while current <= end_date:
        # Skip weekends
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)

    print(f"  Generating data for {len(dates)} business days...")

    # 1. Yield curve data
    print(f"  Seeding yield curve data...")
    for dt in dates:
        # Generate synthetic yield curve with realistic shape
        base_rate = 5.0 + random.uniform(-0.5, 0.5) + (dt - start_date).days * 0.001

        db.insert_yield_curve([
            {
                'date': str(dt),
                'tenor_label': '2Y',
                'tenor_days': 730,
                'spot_rate_continuous': base_rate - 0.1,
                'par_yield': base_rate - 0.05,
                'spot_rate_annual': base_rate,
                'source': 'DEMO',
                'fetched_at': f'{dt}T10:00:00'
            },
            {
                'date': str(dt),
                'tenor_label': '5Y',
                'tenor_days': 1825,
                'spot_rate_continuous': base_rate + 0.5,
                'par_yield': base_rate + 0.55,
                'spot_rate_annual': base_rate + 0.6,
                'source': 'DEMO',
                'fetched_at': f'{dt}T10:00:00'
            },
            {
                'date': str(dt),
                'tenor_label': '10Y',
                'tenor_days': 3650,
                'spot_rate_continuous': base_rate + 1.0,
                'par_yield': base_rate + 1.05,
                'spot_rate_annual': base_rate + 1.1,
                'source': 'DEMO',
                'fetched_at': f'{dt}T10:00:00'
            }
        ])

    # 2. Interbank rates
    print(f"  Seeding interbank rates...")
    for dt in dates:
        on_rate = 0.5 + random.uniform(-0.1, 0.1)

        db.insert_interbank_rates([
            {
                'date': str(dt),
                'tenor_label': 'ON',
                'tenor_days': 1,
                'rate': on_rate,
                'source': 'DEMO',
                'fetched_at': f'{dt}T10:00:00'
            },
            {
                'date': str(dt),
                'tenor_label': '1W',
                'tenor_days': 7,
                'rate': on_rate + 0.1,
                'source': 'DEMO',
                'fetched_at': f'{dt}T10:00:00'
            },
            {
                'date': str(dt),
                'tenor_label': '1M',
                'tenor_days': 30,
                'rate': on_rate + 0.2,
                'source': 'DEMO',
                'fetched_at': f'{dt}T10:00:00'
            }
        ])

    # 3. Auction results
    print(f"  Seeding auction results...")
    auction_dates = dates[::5]  # Every 5th day
    for dt in auction_dates:
        db.insert_auction_results([
            {
                'date': str(dt),
                'instrument_type': 'Government Bond',
                'tenor_label': '5Y',
                'tenor_days': 1825,
                'amount_offered': 5000.0 + random.uniform(-500, 500),
                'amount_sold': 4800.0 + random.uniform(-400, 400),
                'bid_to_cover': 1.2 + random.uniform(-0.1, 0.1),
                'cut_off_yield': 6.0 + random.uniform(-0.2, 0.2),
                'avg_yield': 5.98 + random.uniform(-0.2, 0.2),
                'source': 'DEMO',
                'raw_file': 'demo_auction_001',
                'fetched_at': f'{dt}T10:00:00'
            }
        ])

    # 4. Secondary trading
    print(f"  Seeding secondary trading...")
    for dt in dates:
        db.insert_secondary_trading([
            {
                'date': str(dt),
                'segment': 'Government Bond',
                'bucket_label': 'Credit Institution',
                'volume': 15000.0 + random.uniform(-2000, 2000),
                'value': 16500.0 + random.uniform(-2000, 2000),
                'avg_yield': 6.25 + random.uniform(-0.2, 0.2),
                'source': 'DEMO',
                'raw_file': 'demo_trading_001',
                'fetched_at': f'{dt}T10:00:00'
            }
        ])

    # 5. Policy rates
    print(f"  Seeding policy rates...")
    policy_change_dates = [dates[0], dates[len(dates)//4], dates[len(dates)//2], dates[3*len(dates)//4]]
    for dt in policy_change_dates:
        db.insert_policy_rates([
            {
                'date': str(dt),
                'rate_name': 'Refinancing Rate',
                'rate': 4.5 + random.uniform(-0.25, 0.25),
                'source': 'DEMO',
                'raw_file': 'demo_policy_001',
                'fetched_at': f'{dt}T10:00:00'
            },
            {
                'date': str(dt),
                'rate_name': 'Rediscount Rate',
                'rate': 3.0 + random.uniform(-0.25, 0.25),
                'source': 'DEMO',
                'raw_file': 'demo_policy_002',
                'fetched_at': f'{dt}T10:00:00'
            },
            {
                'date': str(dt),
                'rate_name': 'Base Rate',
                'rate': 4.0 + random.uniform(-0.25, 0.25),
                'source': 'DEMO',
                'raw_file': 'demo_policy_003',
                'fetched_at': f'{dt}T10:00:00'
            }
        ])

    # 6. Ingest runs
    print(f"  Seeding ingest runs...")
    for dt in dates[::7]:  # Weekly
        db.insert_ingest_run(
            started_at=f'{dt}T18:05:00',
            status='success',
            records_processed=random.randint(100, 500),
            duration_seconds=random.uniform(30, 120)
        )

    # 7. DQ runs with some WARNs
    print(f"  Seeding DQ runs...")
    for dt in dates[::7]:  # Weekly
        # Most pass, some WARN
        status = 'PASS' if random.random() > 0.2 else 'WARN'
        passed = 10 if status == 'PASS' else 8
        failed = 0 if status == 'PASS' else 2

        db.insert_dq_run(
            run_at=f'{dt}T18:10:00',
            status=status,
            total_rules=10,
            passed_rules=passed,
            failed_rules=failed
        )

    # 8. Alerts
    print(f"  Seeding alerts...")
    alert_dates = [dates[i] for i in range(0, len(dates), 20) if i < len(dates)]
    for dt in alert_dates:
        db.insert_alert(
            rule_code='RULE_YC_TENOR_COVERAGE',
            severity='WARN' if random.random() > 0.5 else 'INFO',
            message=f'Missing some yield curve tenors on {dt}',
            details={'date': str(dt), 'missing_tenors': ['3Y', '7Y']},
            triggered_at=f'{dt}T18:15:00'
        )

    # 9. Source fingerprints
    print(f"  Seeding source fingerprints...")
    for dt in dates[::30]:  # Monthly
        db.insert_source_fingerprint(
            provider='demo',
            dataset_id='demo_dataset',
            target_date=dt,
            content=f'demo_content_{dt}'.encode(),
            content_type='text/html',
            parse_rowcount=100,
            parse_required_fields_ok=True,
            note='Demo data fingerprint'
        )

    db.close()

    print(f"\n✓ Demo data seeded successfully!")
    print(f"  Date range: {start_date} to {end_date}")
    print(f"  Total business days: {len(dates)}")
    print(f"  Database: {args.db}")
    print(f"\nTo enable demo mode banner, set: DEMO_MODE=true")


def main():
    parser = argparse.ArgumentParser(description='Ops CLI for VN Bond Lab')
    parser.add_argument('--db', default=settings.db_path, help='Database path')

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Backup command
    backup_parser = subparsers.add_parser('backup', help='Create database backup')
    backup_parser.add_argument('--out', help='Output backup path (default: data/backups/bond_lab_YYYYMMDD.duckdb)')
    backup_parser.set_defaults(func=cmd_backup)

    # Restore command
    restore_parser = subparsers.add_parser('restore', help='Restore from backup')
    restore_parser.add_argument('--in', required=True, dest='inp', help='Backup file to restore')
    restore_parser.add_argument('--yes', action='store_true', help='Skip confirmation (requires ALLOW_RESTORE=true)')
    restore_parser.set_defaults(func=cmd_restore)

    # Export command
    export_parser = subparsers.add_parser('export', help='Export dataset to CSV')
    export_parser.add_argument('--dataset', required=True, help='Table name to export')
    export_parser.add_argument('--start', required=True, help='Start date (YYYY-MM-DD)')
    export_parser.add_argument('--end', required=True, help='End date (YYYY-MM-DD)')
    export_parser.add_argument('--out', required=True, help='Output CSV path')
    export_parser.set_defaults(func=cmd_export)

    # Import-interbank command
    import_interbank_parser = subparsers.add_parser('import-interbank', help='Import interbank rates from CSV')
    import_interbank_parser.add_argument('--in', required=True, dest='inp', help='Input CSV path')
    import_interbank_parser.add_argument('--source', default='MANUAL', help='Source label to store (default: MANUAL)')
    import_interbank_parser.add_argument('--tenors', default='3M', help='Comma-separated tenors to import (default: 3M)')
    import_interbank_parser.set_defaults(func=cmd_import_interbank)

    # Verify-backup command
    verify_parser = subparsers.add_parser('verify-backup', help='Verify backup file')
    verify_parser.add_argument('--in', required=True, dest='inp', help='Backup file to verify')
    verify_parser.set_defaults(func=cmd_verify_backup)

    # List-backups command
    list_parser = subparsers.add_parser('list-backups', help='List all backups')
    list_parser.add_argument('--dir', default='data/backups', help='Backup directory')
    list_parser.set_defaults(func=cmd_list_backups)

    # Seed-demo command
    seed_parser = subparsers.add_parser('seed-demo', help='Seed demo data for demonstration')
    seed_parser.add_argument('--days', type=int, default=180, help='Number of days to generate (default: 180)')
    seed_parser.add_argument('--db', default=argparse.SUPPRESS, help='Database path')
    seed_parser.set_defaults(func=cmd_seed_demo)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
