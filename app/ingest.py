"""
Data ingestion pipeline with CLI interface
"""
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional
import time

from app.config import settings
from app.db.schema import DatabaseManager
from app.providers.hnx_yield_curve import HNXYieldCurveProvider
from app.providers.hnx_ftp_pdf import HNXFTPPDFProvider
from app.providers.sbv_interbank import SBVInterbankProvider
from app.providers.abo_market_watch import ABOMarketWatchProvider
from app.providers.hnx_auction import HNXAuctionProvider
from app.providers.hnx_trading import HNXTradingProvider
from app.providers.sbv_policy import SBVPolicyProvider
from app.providers.fred_global import FREDGlobalProvider
from app.providers.lai_suat_rates import LaiSuatRatesProvider

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/ingest.log')
    ]
)
logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Main ingestion pipeline orchestrator"""

    # Default providers for "daily" runs (official/primary sources).
    # Keep this list aligned with:
    # - scripts/run_local_ingest.sh
    # - /api/admin/ingest/daily (manual trigger)
    DEFAULT_DAILY_PROVIDERS = [
        "hnx_yield_curve",
        "hnx_ftp_pdf",
        "hnx_auction",
        "hnx_trading",
        "sbv_interbank",
        "sbv_policy",
        "fred_global",
        "lai_suat_rates",
    ]

    # Provider registry
    PROVIDERS = {
        'hnx_yield_curve': HNXYieldCurveProvider,
        'hnx_ftp_pdf': HNXFTPPDFProvider,
        'sbv_interbank': SBVInterbankProvider,
        'abo': ABOMarketWatchProvider,
        'hnx_auction': HNXAuctionProvider,
        'hnx_trading': HNXTradingProvider,
        'sbv_policy': SBVPolicyProvider,
        'fred_global': FREDGlobalProvider,
        'lai_suat_rates': LaiSuatRatesProvider,
    }

    def __init__(self, db_path: Optional[str] = None, db_manager: Optional[DatabaseManager] = None):
        """Initialize pipeline with database connection (own or injected)."""
        self._owns_db_manager = db_manager is None
        if db_manager is not None:
            self.db_manager = db_manager
            self.db_path = str(getattr(db_manager, "db_path", settings.db_path))
        else:
            self.db_path = db_path or settings.db_path
            self.db_manager = DatabaseManager(self.db_path)
            self.db_manager.connect()
            self.db_manager.initialize_schema()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._owns_db_manager:
            self.db_manager.close()

    def _run_lai_suat_incremental(self, provider, force_scrape: bool = True) -> dict:
        """
        Incrementally sync Lai_suat SQLite -> DuckDB bank_rates.

        This runs inside the server process to avoid DuckDB file lock issues.
        """
        import sqlite3
        from pathlib import Path
        from datetime import datetime as _dt, timedelta as _td

        sqlite_path = Path(settings.lai_suat_db_path)
        if not sqlite_path.exists():
            return {"status": "skipped", "rows_inserted": 0, "error": f"SQLite not found: {sqlite_path}"}

        # Update SQLite first (crawler)
        try:
            provider._maybe_run_scraper_force(force=bool(force_scrape))
        except Exception as e:
            logger.warning("Lai_suat scraper failed (continuing with existing SQLite): %s", e)

        con = sqlite3.connect(str(sqlite_path))
        try:
            sqlite_min, sqlite_max = con.execute(
                "SELECT MIN(observed_day), MAX(observed_day) FROM observations WHERE observed_day IS NOT NULL"
            ).fetchone()
        finally:
            con.close()

        if not sqlite_min or not sqlite_max:
            return {"status": "completed", "rows_inserted": 0, "note": "No observed_day in SQLite"}

        sqlite_min_date = _dt.fromisoformat(str(sqlite_min)).date()
        sqlite_max_date = _dt.fromisoformat(str(sqlite_max)).date()

        duck_max = None
        try:
            duck_max = self.db_manager.con.execute("SELECT MAX(date) FROM bank_rates").fetchone()[0]
        except Exception:
            duck_max = None

        start = sqlite_min_date if duck_max is None else (duck_max + _td(days=1))
        end = sqlite_max_date
        if start > end:
            # Still refresh the latest observed day to capture updated scraped_at / revised rates.
            records = provider.read_range(sqlite_max_date, sqlite_max_date, run_scraper=False)
            rows_inserted = self.db_manager.insert_bank_rates(records) if records else 0
            return {
                "status": "completed",
                "rows_inserted": rows_inserted,
                "start_date": sqlite_max_date.isoformat(),
                "end_date": sqlite_max_date.isoformat(),
                "note": "Refreshed latest day",
            }

        records = provider.read_range(start, end, run_scraper=False)
        rows_inserted = self.db_manager.insert_bank_rates(records) if records else 0
        return {
            "status": "completed",
            "rows_inserted": rows_inserted,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }

    def run_daily(self, providers: Optional[List[str]] = None):
        """
        Run daily ingestion for today's date

        Args:
            providers: List of provider names to run (default: all)
        """
        logger.info("Starting daily ingestion")
        today = date.today()

        if providers is None:
            providers = list(self.DEFAULT_DAILY_PROVIDERS)

        # Filter out FRED if no API key
        if 'fred_global' in providers and not settings.fred_api_key:
            logger.info("FRED API key not provided, skipping fred_global provider")
            providers = [p for p in providers if p != 'fred_global']

        results = {}
        for provider_name in providers:
            try:
                result = self._run_provider(provider_name, today, today)
                results[provider_name] = result
            except Exception as e:
                logger.error(f"Failed to run provider {provider_name}: {e}")
                results[provider_name] = {'status': 'error', 'error': str(e)}

        self._print_summary(results)

        # Run Data Quality checks before analytics compute
        try:
            logger.info("Running Data Quality checks...")
            from app.quality import DataQualityRunner

            dq_runner = DataQualityRunner(self.db_manager)
            # Default behavior: DQ is advisory (does not block analytics).
            # Set DQ_ENFORCE_BLOCK=true to block analytics on DQ FAIL.
            dq_override_block = not getattr(settings, "dq_enforce_block", False)
            dq_result = dq_runner.run_dq_for_date(today, override_block=dq_override_block)

            logger.info(f"DQ check result: {dq_result['status']}")

            if dq_result['should_block']:
                logger.error(f"Data Quality check FAILED. Analytics compute blocked.")
                logger.error(f"Error count: {dq_result['summary']['error_count']}")
                logger.error("Set DQ_ENFORCE_BLOCK=false to allow compute despite DQ FAIL.")
                # Don't compute analytics if DQ failed
                return results

            if dq_result['status'] == 'FAIL':
                logger.warning(
                    "Data Quality status=FAIL but analytics compute will continue (dq_enforce_block=false)."
                )
            if dq_result['status'] == 'WARN':
                logger.warning(f"Data Quality check PASSED with WARNINGS")
                logger.warning(f"Warning count: {dq_result['summary']['warn_count']}")

        except Exception as e:
            logger.warning(f"Failed to run Data Quality checks: {e}")
            logger.warning("Proceeding with analytics compute (DQ check is advisory)")

        # Compute transmission metrics after successful ingestion
        try:
            logger.info("Computing transmission metrics...")
            self._compute_transmission_metrics(today)
            logger.info("Transmission metrics computed successfully")
        except Exception as e:
            logger.warning(f"Failed to compute transmission metrics: {e}")

        # Compute BondY stress metrics
        try:
            logger.info("Computing BondY stress index...")
            self._compute_stress_metrics(today)
            logger.info("BondY stress index computed successfully")
        except Exception as e:
            logger.warning(f"Failed to compute BondY stress: {e}")

        return results

    def run_backfill(
        self,
        start_date: str,
        end_date: str,
        providers: Optional[List[str]] = None
    ):
        """
        Run backfill for a date range

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            providers: List of provider names to run (default: all)
        """
        logger.info(f"Starting backfill from {start_date} to {end_date}")

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError as e:
            logger.error(f"Invalid date format: {e}")
            return

        if providers is None:
            providers = list(self.PROVIDERS.keys())

        results = {}
        for provider_name in providers:
            try:
                result = self._run_provider(provider_name, start, end)
                results[provider_name] = result
            except Exception as e:
                logger.error(f"Failed to run provider {provider_name}: {e}")
                results[provider_name] = {'status': 'error', 'error': str(e)}

        self._print_summary(results)
        return results

    def _run_provider(
        self,
        provider_name: str,
        start_date: date,
        end_date: date
    ) -> dict:
        """
        Run a single provider

        Args:
            provider_name: Name of the provider
            start_date: Start date
            end_date: End date

        Returns:
            Result dictionary with status and metrics
        """
        logger.info(f"Running provider: {provider_name}")

        if provider_name not in self.PROVIDERS:
            raise ValueError(f"Unknown provider: {provider_name}")

        provider_class = self.PROVIDERS[provider_name]

        # Log ingest run start
        run_id = self.db_manager.log_ingest_run(
            provider=provider_name,
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            status='running'
        )

        start_time = time.time()
        total_records = 0

        try:
            with provider_class() as provider:
                # Lai_suat: for daily runs, do incremental sync (SQLite -> DuckDB) in-process.
                if provider_name == "lai_suat_rates" and start_date == end_date:
                    result = self._run_lai_suat_incremental(provider, force_scrape=True)
                    total_records += int(result.get("rows_inserted", 0) or 0)

                    elapsed_time = time.time() - start_time
                    self.db_manager.update_ingest_run(
                        run_id=run_id,
                        status=result.get("status", "completed"),
                        rows_inserted=total_records,
                        error_message=result.get("error"),
                    )

                    return {
                        "status": result.get("status", "completed"),
                        "rows_inserted": total_records,
                        "seconds": round(elapsed_time, 2),
                        "meta": {
                            "start_date": result.get("start_date"),
                            "end_date": result.get("end_date"),
                            "note": result.get("note"),
                        },
                    }

                # Fetch data
                if start_date == end_date:
                    records = provider.fetch(start_date)
                else:
                    records = provider.backfill(start_date, end_date)

                # Separate records by table type
                yield_curve_records = []
                yield_change_records = []
                interbank_records = []
                auction_records = []
                trading_records = []
                policy_records = []
                global_records = []
                bank_rates_records = []

                for record in records:
                    if 'source' in record:
                        source = record['source']

                        # Route to appropriate table
                        # ABO can return both yield curve and interbank records.
                        # Interbank records have a 'rate' field and should NOT be inserted into gov_yield_curve.
                        if source == 'ABO' and 'rate' in record:
                            interbank_records.append(record)
                        elif source in ['HNX_YC', 'ABO']:
                            yield_curve_records.append(record)
                        elif source == 'HNX_FTP_PDF':
                            yield_change_records.append(record)
                        elif source in ['SBV'] and 'rate' in record:
                            interbank_records.append(record)
                        elif source == 'HNX_AUCTION':
                            auction_records.append(record)
                        elif source == 'HNX_TRADING':
                            trading_records.append(record)
                        elif source == 'SBV_POLICY':
                            policy_records.append(record)
                        elif source == 'FRED':
                            global_records.append(record)
                        elif source == 'LAI_SUAT':
                            bank_rates_records.append(record)

                # Insert into database
                if yield_curve_records:
                    count = self.db_manager.insert_yield_curve(yield_curve_records)
                    total_records += count
                    logger.info(f"Inserted {count} yield curve records")

                if yield_change_records:
                    count = self.db_manager.insert_yield_change_stats(yield_change_records)
                    total_records += count
                    logger.info(f"Inserted {count} yield change stats records")

                if interbank_records:
                    count = self.db_manager.insert_interbank_rates(interbank_records)
                    total_records += count
                    logger.info(f"Inserted {count} interbank rate records")

                if auction_records:
                    count = self.db_manager.insert_auction_results(auction_records)
                    total_records += count
                    logger.info(f"Inserted {count} auction result records")

                if trading_records:
                    count = self.db_manager.insert_secondary_trading(trading_records)
                    total_records += count
                    logger.info(f"Inserted {count} secondary trading records")

                if policy_records:
                    count = self.db_manager.insert_policy_rates(policy_records)
                    total_records += count
                    logger.info(f"Inserted {count} policy rate records")

                if global_records:
                    count = self.db_manager.insert_global_rates(global_records)
                    total_records += count
                    logger.info(f"Inserted {count} global rate records")

                if bank_rates_records:
                    count = self.db_manager.insert_bank_rates(bank_rates_records)
                    total_records += count
                    logger.info(f"Inserted {count} bank rate records")

            elapsed_time = time.time() - start_time

            # Update ingest run
            self.db_manager.update_ingest_run(
                run_id=run_id,
                status='completed',
                rows_inserted=total_records
            )

            result = {
                'status': 'completed',
                'rows_inserted': total_records,
                'elapsed_seconds': elapsed_time
            }

            logger.info(f"Provider {provider_name} completed: {total_records} records in {elapsed_time:.2f}s")
            return result

        except Exception as e:
            elapsed_time = time.time() - start_time

            # Log failure to ingest_failures table
            error_type = type(e).__name__

            # Map provider to dataset_id
            dataset_id = f"{provider_name}_data"

            self.db_manager.log_ingest_failure(
                dataset_id=dataset_id,
                provider=provider_name,
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d'),
                error_type=error_type,
                error_message=str(e),
                raw_ref=None
            )

            # Update ingest run with error
            self.db_manager.update_ingest_run(
                run_id=run_id,
                status='failed',
                rows_inserted=total_records,
                error_message=str(e)
            )

            logger.error(f"Provider {provider_name} failed after {elapsed_time:.2f}s: {e}")
            raise

    def run_probe(self, providers: Optional[List[str]] = None, output_file: str = 'reports/provider_probe.json'):
        """
        Probe provider capabilities and generate JSON report

        Args:
            providers: List of provider names to probe (default: all)
            output_file: Path to output JSON report

        Returns:
            Probe results dictionary
        """
        import json
        from datetime import timedelta

        logger.info("Starting provider capability probe...")

        if providers is None:
            providers = list(self.PROVIDERS.keys())

        probe_results = {
            'probe_timestamp': datetime.now().isoformat(),
            'providers': {}
        }

        # Test dates for probing
        today = date.today()
        yesterday = today - timedelta(days=1)
        historical_date = date(2013, 1, 1)  # Earliest documented date

        for provider_name in providers:
            logger.info(f"Probing {provider_name}...")

            provider_class = self.PROVIDERS[provider_name]
            provider_info = {
                'provider_name': provider_name,
                'class_name': provider_class.__name__,
                'capabilities': {
                    'fetch_latest': False,
                    'fetch_yesterday': False,
                    'fetch_historical': False,
                    'backfill_supported': False
                },
                'tests': {},
                'failure_modes': [],
                'earliest_success_date': None,
                'latest_success_date': None
            }

            with provider_class() as provider:
                # Test 1: Fetch latest
                try:
                    logger.info(f"  Testing fetch_latest...")
                    records = provider.fetch(today)
                    provider_info['capabilities']['fetch_latest'] = True
                    provider_info['tests']['fetch_latest'] = {
                        'status': 'success',
                        'records_count': len(records),
                        'date_tested': today.isoformat()
                    }
                    if records:
                        provider_info['latest_success_date'] = today.isoformat()
                except Exception as e:
                    error_type = type(e).__name__
                    provider_info['tests']['fetch_latest'] = {
                        'status': 'failed',
                        'error_type': error_type,
                        'error_message': str(e)[:200]
                    }
                    provider_info['failure_modes'].append(f"fetch_latest: {error_type}")

                # Test 2: Fetch yesterday
                try:
                    logger.info(f"  Testing fetch_yesterday...")
                    records = provider.fetch(yesterday)
                    provider_info['capabilities']['fetch_yesterday'] = True
                    provider_info['tests']['fetch_yesterday'] = {
                        'status': 'success',
                        'records_count': len(records),
                        'date_tested': yesterday.isoformat()
                    }
                    if records:
                        if not provider_info['earliest_success_date']:
                            provider_info['earliest_success_date'] = yesterday.isoformat()
                except Exception as e:
                    error_type = type(e).__name__
                    provider_info['tests']['fetch_yesterday'] = {
                        'status': 'failed',
                        'error_type': error_type,
                        'error_message': str(e)[:200]
                    }
                    provider_info['failure_modes'].append(f"fetch_yesterday: {error_type}")

                # Test 3: Fetch historical (2013-01-01)
                try:
                    logger.info(f"  Testing fetch_historical (2013-01-01)...")
                    records = provider.fetch(historical_date)
                    provider_info['capabilities']['fetch_historical'] = True
                    provider_info['tests']['fetch_historical'] = {
                        'status': 'success',
                        'records_count': len(records),
                        'date_tested': historical_date.isoformat()
                    }
                    if records:
                        provider_info['earliest_success_date'] = historical_date.isoformat()
                except Exception as e:
                    error_type = type(e).__name__
                    provider_info['tests']['fetch_historical'] = {
                        'status': 'failed',
                        'error_type': error_type,
                        'error_message': str(e)[:200]
                    }
                    provider_info['failure_modes'].append(f"fetch_historical: {error_type}")

                # Test 4: Check backfill method signature
                try:
                    logger.info(f"  Checking backfill support...")
                    # Check if backfill method exists
                    if hasattr(provider, 'backfill'):
                        provider_info['capabilities']['backfill_supported'] = True

                        # Try a small backfill (1 day)
                        records = provider.backfill(historical_date, historical_date)
                        provider_info['tests']['backfill_single_day'] = {
                            'status': 'success',
                            'records_count': len(records),
                            'date_range': f"{historical_date.isoformat()} to {historical_date.isoformat()}"
                        }
                    else:
                        provider_info['tests']['backfill_check'] = {
                            'status': 'not_implemented',
                            'message': 'backfill method not found'
                        }
                except Exception as e:
                    error_type = type(e).__name__
                    provider_info['tests']['backfill_check'] = {
                        'status': 'failed',
                        'error_type': error_type,
                        'error_message': str(e)[:200]
                    }

            probe_results['providers'][provider_name] = provider_info

        # Ensure output directory exists
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write JSON report
        with open(output_path, 'w') as f:
            json.dump(probe_results, f, indent=2)

        logger.info(f"Probe report saved to {output_file}")

        # Print summary
        logger.info("=" * 60)
        logger.info("PROBE SUMMARY")
        logger.info("=" * 60)

        for provider_name, info in probe_results['providers'].items():
            caps = info['capabilities']
            logger.info(f"\n{provider_name}:")
            logger.info(f"  fetch_latest:       {'✓' if caps['fetch_latest'] else '✗'}")
            logger.info(f"  fetch_yesterday:    {'✓' if caps['fetch_yesterday'] else '✗'}")
            logger.info(f"  fetch_historical:   {'✓' if caps['fetch_historical'] else '✗'}")
            logger.info(f"  backfill_supported: {'✓' if caps['backfill_supported'] else '✗'}")

            if info['failure_modes']:
                logger.info(f"  failure_modes: {', '.join(info['failure_modes'])}")

            if info['earliest_success_date']:
                logger.info(f"  earliest_success: {info['earliest_success_date']}")

        logger.info("=" * 60)

        return probe_results

    def run_backfill_chunked(
        self,
        start_date: str,
        end_date: str,
        providers: Optional[List[str]] = None,
        chunk: str = 'quarterly'
    ):
        """
        Run backfill with date chunking for safer large-scale backfills

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            providers: List of provider names to run (default: all)
            chunk: Chunk size (daily, weekly, monthly, quarterly, yearly)

        Returns:
            Results dictionary with chunk-by-chunk progress
        """
        logger.info(f"Starting chunked backfill from {start_date} to {end_date} ({chunk} chunks)")

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError as e:
            logger.error(f"Invalid date format: {e}")
            return

        if providers is None:
            providers = list(self.PROVIDERS.keys())

        # Generate date chunks
        chunks = self._generate_date_chunks(start, end, chunk)

        logger.info(f"Generated {len(chunks)} {chunk} chunks")

        results = {
            'chunk_size': chunk,
            'total_chunks': len(chunks),
            'chunks': []
        }

        for chunk_idx, (chunk_start, chunk_end) in enumerate(chunks, 1):
            logger.info(f"Processing chunk {chunk_idx}/{len(chunks)}: {chunk_start} to {chunk_end}")

            chunk_results = {}
            for provider_name in providers:
                try:
                    result = self._run_provider(provider_name, chunk_start, chunk_end)
                    chunk_results[provider_name] = result
                except Exception as e:
                    logger.error(f"Provider {provider_name} failed for chunk {chunk_idx}: {e}")
                    chunk_results[provider_name] = {
                        'status': 'failed',
                        'error': str(e),
                        'chunk': f"{chunk_start} to {chunk_end}"
                    }

            results['chunks'].append({
                'chunk_number': chunk_idx,
                'chunk_start': chunk_start.isoformat(),
                'chunk_end': chunk_end.isoformat(),
                'results': chunk_results
            })

        self._print_chunked_summary(results)
        return results

    def _generate_date_chunks(self, start: date, end: date, chunk_size: str) -> List[tuple[date, date]]:
        """
        Generate date chunks for backfill

        Args:
            start: Start date
            end: End date
            chunk_size: Size of chunks (daily, weekly, monthly, quarterly, yearly)

        Returns:
            List of (chunk_start, chunk_end) tuples
        """
        chunks = []
        current = start

        while current <= end:
            chunk_start = current

            if chunk_size == 'daily':
                chunk_end = current
                current += timedelta(days=1)
            elif chunk_size == 'weekly':
                chunk_end = current + timedelta(days=6)
                current += timedelta(weeks=1)
            elif chunk_size == 'monthly':
                # Move to next month
                if current.month == 12:
                    chunk_end = date(current.year, 12, 31)
                    current = date(current.year + 1, 1, 1)
                else:
                    chunk_end = date(current.year, current.month + 1, 1) - timedelta(days=1)
                    current = date(current.year, current.month + 1, 1)
            elif chunk_size == 'quarterly':
                # Calculate end of quarter
                quarter = (current.month - 1) // 3
                quarter_end_month = (quarter + 1) * 3
                if quarter_end_month > 12:
                    quarter_end_month = 12

                # Last day of quarter
                if quarter_end_month in [1, 4, 7, 10]:
                    next_q_start = quarter_end_month + 2
                    if next_q_start > 12:
                        chunk_end = date(current.year + 1, 1, 1) - timedelta(days=1)
                        current = date(current.year + 1, 1, 1)
                    else:
                        chunk_end = date(current.year, next_q_start, 1) - timedelta(days=1)
                        current = date(current.year, next_q_start, 1)
                else:
                    chunk_end = date(current.year, quarter_end_month + 1, 1) - timedelta(days=1)
                    current = date(current.year, quarter_end_month + 1, 1)
            elif chunk_size == 'yearly':
                # End of year
                chunk_end = date(current.year, 12, 31)
                current = date(current.year + 1, 1, 1)
            else:
                raise ValueError(f"Invalid chunk size: {chunk_size}")

            # Don't go beyond end date
            if chunk_end > end:
                chunk_end = end

            chunks.append((chunk_start, chunk_end))

            if current > end:
                break

        return chunks

    def run_resume(self, dataset_id: Optional[str] = None, providers: Optional[List[str]] = None):
        """
        Resume failed ingestion chunks

        Args:
            dataset_id: Optional dataset ID to filter failures
            providers: Optional list of providers to retry

        Returns:
            Results dictionary
        """
        logger.info("Checking for failed chunks to resume...")

        # Get pending resumes from failures table
        pending_chunks = self.db_manager.get_pending_resumes(dataset_id)

        if not pending_chunks:
            logger.info("No failed chunks found to resume")
            return {'status': 'no_failures', 'resumed': 0}

        logger.info(f"Found {len(pending_chunks)} failed chunks to resume")

        results = {}
        resumed_count = 0

        for chunk_info in pending_chunks:
            provider = chunk_info['provider']
            start = datetime.strptime(chunk_info['start_date'], '%Y-%m-%d').date()
            end = datetime.strptime(chunk_info['end_date'], '%Y-%m-%d').date()

            logger.info(f"Resuming {provider}: {start} to {end}")

            try:
                result = self._run_provider(provider, start, end)
                results[provider] = result
                resumed_count += 1

                # If successful, clear failures for this chunk
                # (Optional: you might want to keep them for audit)

            except Exception as e:
                logger.error(f"Failed to resume {provider} chunk: {e}")
                results[provider] = {
                    'status': 'failed',
                    'error': str(e)
                }

        logger.info(f"Resumed {resumed_count}/{len(pending_chunks)} chunks")
        return {'status': 'completed', 'resumed': resumed_count, 'results': results}

    def _print_chunked_summary(self, results: dict):
        """Print chunked backfill summary"""
        logger.info("=" * 60)
        logger.info("CHUNKED BACKFILL SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Chunk size: {results['chunk_size']}")
        logger.info(f"Total chunks: {results['total_chunks']}")

        for chunk_info in results['chunks']:
            chunk_num = chunk_info['chunk_number']
            chunk_range = f"{chunk_info['chunk_start']} to {chunk_info['chunk_end']}"

            logger.info(f"\nChunk {chunk_num}: {chunk_range}")

            for provider, result in chunk_info['results'].items():
                status = result.get('status', 'unknown')
                rows = result.get('rows_inserted', 0)
                logger.info(f"  {provider:20s} | {status:10s} | {rows:5d} rows")

        logger.info("=" * 60)

    def _print_summary(self, results: dict):
        """Print ingestion summary"""
        logger.info("=" * 60)
        logger.info("INGESTION SUMMARY")
        logger.info("=" * 60)

        for provider_name, result in results.items():
            status = result.get('status', 'unknown')
            rows = result.get('rows_inserted', 0)
            elapsed = result.get('elapsed_seconds', 0)

            logger.info(f"{provider_name:20s} | {status:10s} | {rows:5d} rows | {elapsed:6.2f}s")

        logger.info("=" * 60)

    def _compute_transmission_metrics(self, target_date: date):
        """
        Compute and store transmission metrics for a specific date

        Args:
            target_date: Date to compute metrics for

        Returns:
            Tuple of (metrics_dict, alerts_list)
        """
        from app.analytics.transmission import TransmissionAnalytics

        analytics = TransmissionAnalytics(self.db_manager)
        metrics, alerts = analytics.compute_daily_metrics(target_date)

        # Insert metrics
        self.db_manager.insert_transmission_metrics(
            target_date.strftime('%Y-%m-%d'),
            metrics
        )

        # Insert alerts
        if alerts:
            self.db_manager.insert_transmission_alerts(
                target_date.strftime('%Y-%m-%d'),
                alerts
            )

        logger.info(f"Computed {len(metrics)} metrics and {len(alerts)} alerts for {target_date}")

        return metrics, alerts

    def _compute_stress_metrics(self, target_date: date):
        """
        Compute BondY stress metrics for a specific date

        Args:
            target_date: Date to compute stress metrics for

        Returns:
            Tuple of (stress_index, regime_bucket, components_dict)
        """
        from app.analytics.stress_model import BondYStressModel
        import json

        stress_model = BondYStressModel(self.db_manager)
        stress_index, regime_bucket, components = stress_model.compute_stress_index(target_date)

        # Insert stress record
        driver_json = json.dumps(components.get('drivers', []))
        self.db_manager.insert_bondy_stress(
            target_date.strftime('%Y-%m-%d'),
            stress_index,
            regime_bucket,
            driver_json
        )

        # Compute global comparators (optional)
        try:
            comparators = stress_model.compute_global_comparators(target_date)

            # Store any global alerts
            if comparators.get('alerts'):
                from app.analytics.transmission import TransmissionAnalytics
                analytics = TransmissionAnalytics(self.db_manager)

                # Convert to transmission alert format
                for alert in comparators['alerts']:
                    # Store in transmission_alerts table
                    self.db_manager.insert_transmission_alerts(
                        target_date.strftime('%Y-%m-%d'),
                        [alert]
                    )

                logger.info(f"Generated {len(comparators['alerts'])} global alerts")
        except Exception as e:
            logger.warning(f"Failed to compute global comparators: {e}")

        logger.info(f"Computed BondY stress: {stress_index}/100, bucket: {regime_bucket}")

        return stress_index, regime_bucket, components


def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Vietnamese Bond Data Lab - Ingestion Pipeline')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Daily command
    daily_parser = subparsers.add_parser('daily', help='Run daily ingestion')
    daily_parser.add_argument(
        '--providers',
        nargs='+',
        choices=list(IngestionPipeline.PROVIDERS.keys()),
        help='Providers to run (default: all)'
    )

    # Backfill command
    backfill_parser = subparsers.add_parser('backfill', help='Run backfill')
    backfill_parser.add_argument(
        '--start',
        required=True,
        help='Start date (YYYY-MM-DD)'
    )
    backfill_parser.add_argument(
        '--end',
        required=True,
        help='End date (YYYY-MM-DD)'
    )
    backfill_parser.add_argument(
        '--providers',
        nargs='+',
        choices=list(IngestionPipeline.PROVIDERS.keys()),
        help='Providers to run (default: all)'
    )

    # Chunked backfill command
    chunked_parser = subparsers.add_parser('backfill-chunked', help='Run chunked backfill for large date ranges')
    chunked_parser.add_argument(
        '--start',
        required=True,
        help='Start date (YYYY-MM-DD)'
    )
    chunked_parser.add_argument(
        '--end',
        required=True,
        help='End date (YYYY-MM-DD)'
    )
    chunked_parser.add_argument(
        '--providers',
        nargs='+',
        choices=list(IngestionPipeline.PROVIDERS.keys()),
        help='Providers to run (default: all)'
    )
    chunked_parser.add_argument(
        '--chunk',
        choices=['daily', 'weekly', 'monthly', 'quarterly', 'yearly'],
        default='quarterly',
        help='Chunk size for backfill (default: quarterly)'
    )

    # Resume command
    resume_parser = subparsers.add_parser('resume', help='Resume failed ingestion chunks')
    resume_parser.add_argument(
        '--dataset',
        help='Dataset ID to filter (optional, resumes all failures if not specified)'
    )
    resume_parser.add_argument(
        '--providers',
        nargs='+',
        choices=list(IngestionPipeline.PROVIDERS.keys()),
        help='Providers to retry (default: all with failures)'
    )

    # Probe command
    probe_parser = subparsers.add_parser('probe', help='Probe provider capabilities')
    probe_parser.add_argument(
        '--providers',
        nargs='+',
        choices=list(IngestionPipeline.PROVIDERS.keys()),
        help='Providers to probe (default: all)'
    )
    probe_parser.add_argument(
        '--output',
        default='reports/provider_probe.json',
        help='Output JSON file path (default: reports/provider_probe.json)'
    )

    # Catalog command
    catalog_parser = subparsers.add_parser('catalog', help='List all available datasets')
    catalog_parser.add_argument(
        '--format',
        choices=['table', 'json'],
        default='table',
        help='Output format (default: table)'
    )
    catalog_parser.add_argument(
        '--output',
        help='Output file path (for JSON format)'
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Ensure logs directory exists
    Path('logs').mkdir(exist_ok=True)

    # Run pipeline
    with IngestionPipeline() as pipeline:
        if args.command == 'daily':
            pipeline.run_daily(providers=args.providers)
        elif args.command == 'backfill':
            pipeline.run_backfill(
                start_date=args.start,
                end_date=args.end,
                providers=args.providers
            )
        elif args.command == 'backfill-chunked':
            pipeline.run_backfill_chunked(
                start_date=args.start,
                end_date=args.end,
                providers=args.providers,
                chunk=args.chunk
            )
        elif args.command == 'resume':
            pipeline.run_resume(
                dataset_id=args.dataset,
                providers=args.providers
            )
        elif args.command == 'probe':
            pipeline.run_probe(providers=args.providers, output_file=args.output)
        elif args.command == 'catalog':
            from app.dataset_catalog import main as catalog_main
            # Pass args to catalog
            import sys
            sys.argv = ['dataset_catalog', '--format', args.format]
            if args.output:
                sys.argv.extend(['--output', args.output])
            catalog_main()


if __name__ == '__main__':
    main()
