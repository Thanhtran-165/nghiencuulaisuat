"""Ingest logic for storing parsed data into database."""

import json
from typing import List, Dict, Any, Optional, Set, Tuple
from .db import Database
from .utils import compute_content_hash, logger


class Ingester:
    """Handle ingestion of parsed records into database."""

    # Whitelist of valid drop reasons
    VALID_DROP_REASONS = {
        'missing_bank', 'missing_term_for_deposit', 'out_of_range',
        'non_numeric', 'duplicate_record', 'parse_error'
    }

    def __init__(self, db: Database):
        """
        Initialize ingester.

        Args:
            db: Database instance
        """
        self.db = db

    def dedup_records(self, records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
        """
        Deduplicate records based on key fields.

        Args:
            records: List of records to deduplicate

        Returns:
            Tuple of (deduplicated_records, duplicate_count)
        """
        seen: Set[str] = set()
        deduped = []

        for record in records:
            # Create dedup key
            key_parts = [
                record.get('bank_name', ''),
                record.get('series', ''),
                str(record.get('term_months', '')),
                str(record.get('rate_min_pct', '')),
                str(record.get('rate_max_pct', '')),
                str(record.get('rate_pct', ''))
            ]
            key = '|'.join(key_parts)

            if key not in seen:
                seen.add(key)
                deduped.append(record)

        duplicate_count = len(records) - len(deduped)
        if duplicate_count > 0:
            logger.info(f"Deduplicated {duplicate_count} records")

        return deduped, duplicate_count

    def ingest_records(
        self,
        records: List[Dict[str, Any]],
        url: str,
        scraped_at: str,
        html_content: str,
        page_updated_text: Optional[str] = None,
        strategy_used: Optional[str] = None,
        parse_version: Optional[str] = None,
        http_status: Optional[int] = None,
        fetched_at: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ingest parsed records into database with statistics tracking.

        Args:
            records: List of canonical records
            url: Source URL
            scraped_at: Scrape timestamp
            html_content: Original HTML content for hash
            page_updated_text: Extracted update text from page
            strategy_used: Parsing strategy used (A or B)
            parse_version: Parser version
            http_status: HTTP status code
            fetched_at: Fetch completion timestamp

        Returns:
            Ingestion metadata with counts and status
        """
        if not records:
            return {
                'status': 'skipped',
                'reason': 'no_records',
                'records_count': 0,
                'extracted': 0,
                'inserted': 0,
                'dropped_duplicate': 0,
                'dropped_invalid': 0,
                'dropped_reason_json': json.dumps({})
            }

        # Deduplicate records
        deduped_records, duplicate_count = self.dedup_records(records)

        # Track drop reasons
        dropped_reasons: Dict[str, int] = {}

        # Validate records and collect drop reasons
        valid_records = []
        for record in deduped_records:
            drop_reason = self._validate_record(record)

            if drop_reason:
                dropped_reasons[drop_reason] = dropped_reasons.get(drop_reason, 0) + 1
            else:
                valid_records.append(record)

        dropped_invalid_count = len(deduped_records) - len(valid_records)

        # Observed day should reflect Vietnam local date (UTC+7), not raw UTC date.
        observed_day = None
        try:
            if scraped_at:
                from datetime import datetime, timedelta

                dt = datetime.fromisoformat(scraped_at.replace("Z", "+00:00"))
                observed_day = (dt + timedelta(hours=7)).date().isoformat()
        except Exception:
            observed_day = (scraped_at or "")[:10] if scraped_at else None

        # Compute content hashes:
        # - raw: detect real page changes across days
        # - salted: allow daily snapshots even if HTML is unchanged
        raw_content_hash = compute_content_hash(html_content)
        content_hash = compute_content_hash(html_content, salt=observed_day)

        # Check if source already exists with same content
        existing_source_id = self.db.check_source_exists(url, content_hash)

        if existing_source_id:
            logger.info(f"Content unchanged for {url}, skipping ingestion")
            return {
                'status': 'skipped',
                'reason': 'content_unchanged',
                'existing_source_id': existing_source_id,
                'records_count': len(records),
                'extracted': len(records),
                'inserted': 0,
                'dropped_duplicate': duplicate_count,
                'dropped_invalid': dropped_invalid_count,
                'dropped_reason_json': json.dumps(dropped_reasons)
            }

        # Insert new source with metadata
        source_id = self.db.insert_source(
            url=url,
            scraped_at=scraped_at,
            content_hash=content_hash,
            page_updated_text=page_updated_text,
            content_hash_raw=raw_content_hash,
            strategy_used=strategy_used,
            parse_version=parse_version,
            http_status=http_status,
            fetched_at=fetched_at,
            record_count_extracted=len(records),
            record_count_inserted=0,  # Will update after insertion
            dropped_duplicate_count=duplicate_count,
            dropped_invalid_count=dropped_invalid_count,
            dropped_reason_json=json.dumps(dropped_reasons)
        )
        logger.info(f"Created new source: {source_id}")

        # Ingest valid records
        inserted_count = 0
        for record in valid_records:
            if self._ingest_record(record, source_id, observed_day=observed_day):
                inserted_count += 1

        # Persist inserted count for monitoring/diagnostics.
        try:
            self.db.update_source_record_count_inserted(source_id, inserted_count)
        except Exception:
            # Non-fatal; keep ingestion success even if stats update fails.
            pass

        logger.info(f"Ingested {inserted_count}/{len(records)} records "
                   f"(dupes: {duplicate_count}, invalid: {dropped_invalid_count})")

        return {
            'status': 'success',
            'source_id': source_id,
            'records_count': len(records),
            'extracted': len(records),
            'inserted': inserted_count,
            'dropped_duplicate': duplicate_count,
            'dropped_invalid': dropped_invalid_count,
            'dropped_reason_json': json.dumps(dropped_reasons)
        }

    def _validate_record(self, record: Dict[str, Any]) -> Optional[str]:
        """
        Validate a record and return drop reason if invalid.

        Args:
            record: Record to validate

        Returns:
            Drop reason string if invalid, None if valid
        """
        # Check bank name
        if not record.get('bank_name'):
            return 'missing_bank'

        # Deposit records must have term
        if record.get('product_group') == 'deposit':
            if record.get('term_months') is None:
                return 'missing_term_for_deposit'

        # Check that at least one rate is set
        if (record.get('rate_min_pct') is None and
            record.get('rate_max_pct') is None and
            record.get('rate_pct') is None):
            return 'non_numeric'

        return None

    def _ingest_record(self, record: Dict[str, Any], source_id: int, observed_day: Optional[str] = None) -> bool:
        """
        Ingest a single record.

        Args:
            record: Canonical record dictionary
            source_id: Source ID

        Returns:
            True if inserted, False if duplicate or error
        """
        try:
            # Upsert bank
            bank_id = self.db.upsert_bank(record['bank_name'])

            # Upsert series
            series_id = self.db.upsert_series(
                product_group=record['product_group'],
                code=record['series'],
                description=None
            )

            # For deposit, upsert term
            term_id = None
            if record['product_group'] == 'deposit':
                term_id = self.db.upsert_term(
                    label=record['term_label'],
                    months=record['term_months']
                )

            # Insert observation
            obs_id = self.db.insert_observation(
                source_id=source_id,
                bank_id=bank_id,
                series_id=series_id,
                term_id=term_id,
                rate_min_pct=record.get('rate_min_pct'),
                rate_max_pct=record.get('rate_max_pct'),
                rate_pct=record.get('rate_pct'),
                observed_day=observed_day,
                raw_value=record.get('raw_value'),
                parse_warnings=record.get('parse_warnings')
            )

            return obs_id is not None

        except Exception as e:
            logger.error(f"Error ingesting record: {e}")
            return False

    def get_latest_records(self, url: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get latest records from database.

        Args:
            url: Optional URL to filter by

        Returns:
            List of observation records
        """
        source_id = self.db.get_latest_source_id(url)

        if not source_id:
            return []

        return self.db.get_observations_by_source(source_id)
