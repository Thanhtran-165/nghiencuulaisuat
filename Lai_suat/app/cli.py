"""CLI interface for bank interest rate scraper."""

import argparse
import sys
import os
from .db import Database
from .scraper import Scraper
from .ingest import Ingester
from .export import Exporter
from .monitoring import (
    check_anomaly,
    compute_final_exit_code,
    format_anomaly_message,
    format_fatal_error_message
)
from .utils import logger


def cmd_init_db(args):
    """Initialize database schema."""
    db = Database(args.db)
    db.init_schema()
    print(f"Database initialized at {args.db}")


def cmd_scrape(args):
    """Scrape URLs and ingest data with anomaly detection."""
    db = Database(args.db)

    # Check if database exists
    if not os.path.exists(args.db):
        print(f"Database not found at {args.db}")
        print("Run 'python -m app.cli init-db --db data/rates.db' first")
        sys.exit(1)

    # Ensure schema is up-to-date before scraping (idempotent).
    # This is important for consumers that rely on newer columns like `observed_day`.
    try:
        db.init_schema()
    except Exception as e:
        print(f"Warning: failed to ensure schema: {e}")
        logger.warning(f"Failed to ensure schema before scrape: {e}")

    # Get CLI options
    anomaly_threshold = getattr(args, 'anomaly_threshold', 0.30)
    no_anomaly_exit = getattr(args, 'no_anomaly_exit', False)

    scraper = Scraper()
    ingester = Ingester(db)

    # Track overall status for exit code
    has_fatal = False
    has_anomaly = False

    if args.all:
        # Scrape all URLs
        print("Scraping all URLs...")
        results = scraper.scrape_all()

        for product_type, (records, metadata) in results.items():
            url = metadata.get('url', 'unknown')

            # Check for fatal scrape failure
            if 'error' in metadata:
                error_msg = format_fatal_error_message(
                    url, metadata['error'], metadata.get('strategy')
                )
                print(error_msg)
                logger.error(error_msg)
                has_fatal = True
                continue

            print(f"\nScraped {product_type}:")
            print(f"  Records: {len(records)}")
            print(f"  Strategy: {metadata['parse_metadata']['strategy']}")
            print(f"  Description: {metadata['parse_metadata']['description']}")

            # Ingest records with metadata
            try:
                result = ingester.ingest_records(
                    records=records,
                    url=metadata['url'],
                    scraped_at=metadata['scraped_at'],
                    html_content=metadata['html_content'],
                    page_updated_text=metadata['page_metadata'].get('page_updated_text'),
                    strategy_used=metadata['parse_metadata']['strategy'],
                    parse_version='1.0',  # Can be git hash or constant
                    http_status=metadata.get('http_status'),
                    fetched_at=metadata.get('fetched_at')
                )

                # Display ingest results
                if result['status'] == 'success':
                    print(f"  Extracted: {result['extracted']}")
                    print(f"  Inserted: {result['inserted']}")
                    print(f"  Dropped (dupes): {result['dropped_duplicate']}")
                    print(f"  Dropped (invalid): {result['dropped_invalid']}")
                    print(f"  Source ID: {result['source_id']}")
                elif result['status'] == 'skipped':
                    print(f"  Skipped: {result['reason']}")
                    if result['reason'] == 'content_unchanged':
                        print(f"  Existing Source ID: {result['existing_source_id']}")

                # Check for anomaly (even if skipped due to content_unchanged).
                # If we inserted a new source row, compare against the previous run by excluding it.
                new_count = result['extracted']
                exclude_source_id = result.get('source_id')

                with db.get_connection() as conn:
                    is_anomaly, info = check_anomaly(
                        conn,
                        url,
                        new_count,
                        anomaly_threshold,
                        exclude_source_id=exclude_source_id,
                    )

                    if is_anomaly:
                        has_anomaly = True
                        warning_msg = format_anomaly_message(url, info)
                        print(f"  {warning_msg}")
                        logger.warning(warning_msg)

            except Exception as e:
                print(f"  Failed to ingest {product_type}: {e}")
                logger.error(f"Failed to ingest {product_type}: {e}")
                has_fatal = True

    elif args.url:
        # Scrape single URL
        print(f"Scraping {args.url}...")
        url = args.url

        try:
            # Determine if deposit or loan
            if 'gui-tiet-kiem' in url:
                records, metadata = scraper.scrape_deposit()
            elif 'so-sanh-lai-suat-vay' in url:
                records, metadata = scraper.scrape_loan()
            else:
                print(f"Unknown URL type: {url}")
                sys.exit(1)

            print(f"Records: {len(records)}")
            print(f"Strategy: {metadata['parse_metadata']['strategy']}")
            print(f"Description: {metadata['parse_metadata']['description']}")

            # Ingest records with metadata
            result = ingester.ingest_records(
                records=records,
                url=metadata['url'],
                scraped_at=metadata['scraped_at'],
                html_content=metadata['html_content'],
                page_updated_text=metadata['page_metadata'].get('page_updated_text'),
                strategy_used=metadata['parse_metadata']['strategy'],
                parse_version='1.0',
                http_status=metadata.get('http_status'),
                fetched_at=metadata.get('fetched_at')
            )

            # Display ingest results
            if result['status'] == 'success':
                print(f"Extracted: {result['extracted']}")
                print(f"Inserted: {result['inserted']}")
                print(f"Dropped (dupes): {result['dropped_duplicate']}")
                print(f"Dropped (invalid): {result['dropped_invalid']}")
                print(f"Source ID: {result['source_id']}")
            elif result['status'] == 'skipped':
                print(f"Skipped: {result['reason']}")
                if result['reason'] == 'content_unchanged':
                    print(f"Existing Source ID: {result['existing_source_id']}")

            # Check for anomaly (even if skipped due to content_unchanged).
            # If we inserted a new source row, compare against the previous run by excluding it.
            new_count = result['extracted']
            exclude_source_id = result.get('source_id')

            with db.get_connection() as conn:
                is_anomaly, info = check_anomaly(
                    conn,
                    url,
                    new_count,
                    anomaly_threshold,
                    exclude_source_id=exclude_source_id,
                )

                if is_anomaly:
                    has_anomaly = True
                    warning_msg = format_anomaly_message(url, info)
                    print(warning_msg)
                    logger.warning(warning_msg)

        except Exception as e:
            error_msg = format_fatal_error_message(url, str(e), "none")
            print(error_msg)
            logger.error(error_msg)
            has_fatal = True

    else:
        print("Either --all or --url must be specified")
        sys.exit(1)

    # Compute and return final exit code
    exit_code = compute_final_exit_code(has_fatal, has_anomaly, no_anomaly_exit)
    sys.exit(exit_code)


def cmd_export(args):
    """Export data to CSV files."""
    db = Database(args.db)

    # Check if database exists
    if not os.path.exists(args.db):
        print(f"Database not found at {args.db}")
        sys.exit(1)

    exporter = Exporter(db)

    if args.latest:
        # Export latest merged data
        print("Exporting latest merged data...")
        files = exporter.export_latest(args.out)

        for name, path in files.items():
            if path:
                print(f"  Exported {name}: {path}")
            else:
                print(f"  Skipped {name}")

    elif args.raw_all_sources:
        # Export per-source data without merging (debug mode)
        print("Exporting per-source data without merging (debug mode)...")
        files = exporter.export_latest_raw_all_sources(args.out)

        for name, path in files.items():
            if path:
                print(f"  Exported {name}: {path}")
            else:
                print(f"  Skipped {name}")

    elif args.source_id:
        # Export specific source
        print(f"Exporting source {args.source_id}...")
        files = exporter.export_source(args.source_id, args.out)

        for name, path in files.items():
            if path:
                print(f"  Exported {name}: {path}")
            else:
                print(f"  Skipped {name}")

    else:
        print("Either --latest, --raw-all-sources, or --source-id must be specified")
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Bank Interest Rate Scraper',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--db', default='data/rates.db',
                       help='Path to SQLite database (default: data/rates.db)')

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # init-db command
    parser_init = subparsers.add_parser('init-db', help='Initialize database schema')
    parser_init.set_defaults(func=cmd_init_db)

    # scrape command
    parser_scrape = subparsers.add_parser('scrape', help='Scrape URLs and ingest data')
    scrape_group = parser_scrape.add_mutually_exclusive_group(required=True)
    scrape_group.add_argument('--all', action='store_true',
                             help='Scrape all URLs')
    scrape_group.add_argument('--url', help='Scrape specific URL')
    parser_scrape.add_argument('--anomaly-threshold', type=float, default=0.30,
                              help='Anomaly detection threshold (default: 0.30 = 30%% drop)')
    parser_scrape.add_argument('--no-anomaly-exit', action='store_true',
                              help='Do not exit with code 2 on anomaly (log warning only)')
    parser_scrape.set_defaults(func=cmd_scrape)

    # export command
    parser_export = subparsers.add_parser('export', help='Export data to CSV')
    export_group = parser_export.add_mutually_exclusive_group(required=True)
    export_group.add_argument('--latest', action='store_true',
                             help='Export latest merged data')
    export_group.add_argument('--raw-all-sources', action='store_true',
                             help='Export per-source data without merging (debug mode)')
    export_group.add_argument('--source-id', type=int,
                             help='Export specific source ID')
    parser_export.add_argument('--out', default='out',
                             help='Output directory (default: out)')
    parser_export.set_defaults(func=cmd_export)

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Execute command
    args.func(args)


if __name__ == '__main__':
    main()
