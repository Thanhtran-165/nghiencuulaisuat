#!/usr/bin/env python3
"""
Scrape Job Runner

Production-friendly script to run scraping jobs with logging and monitoring.
Can be used standalone or scheduled via cron/APScheduler.

Usage:
    python scripts/run_scrape_job.py --all
    python scripts/run_scrape_job.py --source timo_deposit
    python scripts/run_scrape_job.py --kind deposit --anomaly-threshold 0.30

Exit Codes:
    0: Success (no anomalies)
    2: Anomaly detected (record count drop > threshold)
    3: Fatal scrape failure
"""

import sys
import os
import logging
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.cli import scrape as scrape_module
from app.source_registry import get_all_source_ids, get_source, get_sources_by_kind


def setup_logging(log_dir: str = "logs") -> logging.Logger:
    """
    Setup logging with file and console handlers.

    Args:
        log_dir: Directory for log files (created if not exists)

    Returns:
        Configured logger instance
    """
    # Ensure log directory exists
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    # Create logger
    logger = logging.getLogger("scrape_job")
    logger.setLevel(logging.INFO)

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    # File handler - daily rotating logs
    log_filename = datetime.now().strftime("scrape_%Y%m%d.log")
    log_filepath = Path(log_dir) / log_filename

    file_handler = logging.FileHandler(log_filepath, encoding='utf-8')
    file_handler.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def main():
    """Main entry point for scrape job runner"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run scraping job with logging and monitoring"
    )
    parser.add_argument(
        "--db",
        default="data/rates.db",
        help="Path to SQLite database (default: data/rates.db)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scrape all sources from registry"
    )
    parser.add_argument(
        "--source",
        type=str,
        help="Scrape specific source by source_id"
    )
    parser.add_argument(
        "--kind",
        type=str,
        choices=["deposit", "loan"],
        help="Scrape all sources of a specific kind"
    )
    parser.add_argument(
        "--anomaly-threshold",
        type=float,
        default=0.30,
        help="Anomaly detection threshold (default: 0.30 = 30%%)"
    )
    parser.add_argument(
        "--no-anomaly-exit",
        action="store_true",
        help="Log anomalies but don't exit with code 2"
    )

    args = parser.parse_args()

    # Setup logging
    logger = setup_logging()

    # Build URL list based on arguments
    urls = []
    source_ids = []

    if args.all:
        # Scrape all sources from registry
        source_ids = get_all_source_ids()
        sources = [get_source(sid) for sid in source_ids]
        urls = [s.url for s in sources]
        logger.info(f"Scraping ALL sources ({len(urls)} sources): {', '.join(source_ids)}")

    elif args.source:
        # Scrape specific source
        try:
            source = get_source(args.source)
            source_ids = [args.source]
            urls = [source.url]
            logger.info(f"Scraping source: {args.source} ({source.url})")
        except KeyError as e:
            logger.error(f"Source not found: {args.source}")
            logger.error(f"Available sources: {get_all_source_ids()}")
            sys.exit(1)

    elif args.kind:
        # Scrape all sources of a kind
        sources = get_sources_by_kind(args.kind)
        source_ids = [s.source_id for s in sources]
        urls = [s.url for s in sources]
        logger.info(f"Scraping {args.kind} sources ({len(urls)} sources): {', '.join(source_ids)}")

    else:
        logger.error("Must specify --all, --source <source_id>, or --kind <deposit|loan>")
        parser.print_help()
        sys.exit(1)

    # Log job start
    logger.info("=" * 80)
    logger.info("SCRAPE JOB STARTED")
    logger.info(f"Started at: {datetime.now().isoformat()}")
    logger.info(f"Database: {args.db}")
    logger.info(f"Sources: {', '.join(source_ids)}")
    logger.info(f"Anomaly threshold: {args.anomaly_threshold:.2%}")
    logger.info("=" * 80)

    # Run scrape (delegating to existing CLI module)
    # The scrape module handles exit codes, so we just pass through
    try:
        scrape_module.scrape_all(
            db_path=args.db,
            urls=urls,
            anomaly_threshold=args.anomaly_threshold,
            no_anomaly_exit=args.no_anomaly_exit
        )
    except SystemExit as e:
        # Capture exit code from scrape module
        exit_code = e.code if e.code is not None else 0

        # Log job completion
        logger.info("=" * 80)
        logger.info("SCRAPE JOB COMPLETED")
        logger.info(f"Finished at: {datetime.now().isoformat()}")
        logger.info(f"Exit code: {exit_code} ({'SUCCESS' if exit_code == 0 else 'ANOMALY' if exit_code == 2 else 'FATAL'})")
        logger.info("=" * 80)

        sys.exit(exit_code)

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        logger.info("=" * 80)
        logger.info("SCRAPE JOB FAILED")
        logger.info(f"Finished at: {datetime.now().isoformat()}")
        logger.info(f"Exit code: 3 (FATAL)")
        logger.info("=" * 80)
        sys.exit(3)


if __name__ == "__main__":
    main()
