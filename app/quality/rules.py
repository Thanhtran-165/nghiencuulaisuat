"""
Data Quality Rules Definitions

Defines validation rules for each dataset type.
Rules return severity (INFO/WARN/ERROR) and detailed messages.
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)


class DataQualityRule:
    """Base class for data quality rules"""

    def __init__(self, rule_code: str, name: str, description: str):
        self.rule_code = rule_code
        self.name = name
        self.description = description

    def check(self, db_manager, target_date: date) -> Tuple[bool, str, str, Dict[str, Any]]:
        """
        Run the rule check

        Returns:
            (passed, severity, message, details)
            - passed: bool - True if rule passed
            - severity: str - 'INFO', 'WARN', or 'ERROR'
            - message: str - Human-readable message
            - details: dict - Additional details for debugging
        """
        raise NotImplementedError


class YieldCurveTenorCoverage(DataQualityRule):
    """Check if required tenors are present in yield curve data"""

    REQUIRED_TENORS = ['2Y', '5Y', '10Y']

    def __init__(self):
        super().__init__(
            rule_code='RULE_YC_TENOR_COVERAGE',
            name='Yield Curve Tenor Coverage',
            description='Checks if required tenors (2Y, 5Y, 10Y) are present or have nearest mapping'
        )

    def check(self, db_manager, target_date: date) -> Tuple[bool, str, str, Dict[str, Any]]:
        try:
            # Get yield curve data for target date
            yc_data = db_manager.get_latest_yield_curve(str(target_date))

            if not yc_data:
                return False, 'ERROR', 'No yield curve data found for target date', {
                    'expected_tenors': self.REQUIRED_TENORS,
                    'found_tenors': []
                }

            found_tenors = [row['tenor_label'] for row in yc_data]
            missing_tenors = [t for t in self.REQUIRED_TENORS if t not in found_tenors]

            if missing_tenors:
                # Check if we have nearest mappings (e.g., 3Y instead of 2Y)
                has_mapping = any(row['tenor_label'] for row in yc_data if row['tenor_label'])

                if has_mapping and len(found_tenors) >= 2:
                    # At least have some data
                    return False, 'WARN', f'Missing required tenors: {missing_tenors}. Found: {found_tenors}', {
                        'expected_tenors': self.REQUIRED_TENORS,
                        'found_tenors': found_tenors,
                        'missing_tenors': missing_tenors
                    }
                else:
                    # Critical - missing most data
                    return False, 'ERROR', f'Missing critical tenors: {missing_tenors}', {
                        'expected_tenors': self.REQUIRED_TENORS,
                        'found_tenors': found_tenors,
                        'missing_tenors': missing_tenors
                    }

            return True, 'INFO', f'All required tenors present: {found_tenors}', {
                'found_tenors': found_tenors
            }

        except Exception as e:
            logger.error(f"Error checking yield curve tenor coverage: {e}")
            return False, 'ERROR', f'Rule execution failed: {str(e)}', {'error': str(e)}


class YieldCurveRangeSanity(DataQualityRule):
    """Check if yield values are within reasonable bounds"""

    MIN_YIELD = -1.0  # -1%
    MAX_YIELD = 30.0  # 30%

    def __init__(self):
        super().__init__(
            rule_code='RULE_YC_RANGE_SANITY',
            name='Yield Curve Range Sanity',
            description=f'Checks if yields are between {self.MIN_YIELD}% and {self.MAX_YIELD}%'
        )

    def check(self, db_manager, target_date: date) -> Tuple[bool, str, str, Dict[str, Any]]:
        try:
            yc_data = db_manager.get_latest_yield_curve(str(target_date))

            if not yc_data:
                return True, 'INFO', 'No yield curve data to check', {}

            out_of_range = []
            for row in yc_data:
                yield_val = row.get('spot_rate_annual')
                if yield_val is not None:
                    if yield_val < self.MIN_YIELD or yield_val > self.MAX_YIELD:
                        out_of_range.append({
                            'tenor': row['tenor_label'],
                            'yield': yield_val
                        })

            if out_of_range:
                # Check if extreme values
                extreme = any(v['yield'] < -5 or v['yield'] > 50 for v in out_of_range)

                if extreme:
                    return False, 'ERROR', f'Extreme yield values detected: {out_of_range}', {
                        'out_of_range': out_of_range,
                        'min_yield': self.MIN_YIELD,
                        'max_yield': self.MAX_YIELD
                    }
                else:
                    return False, 'WARN', f'Yields outside normal range: {out_of_range}', {
                        'out_of_range': out_of_range,
                        'min_yield': self.MIN_YIELD,
                        'max_yield': self.MAX_YIELD
                    }

            return True, 'INFO', f'All yields within range [{self.MIN_YIELD}%, {self.MAX_YIELD}%]', {
                'checked_count': len(yc_data)
            }

        except Exception as e:
            logger.error(f"Error checking yield curve range: {e}")
            return False, 'ERROR', f'Rule execution failed: {str(e)}', {'error': str(e)}


class YieldCurveDayGap(DataQualityRule):
    """Check if there are gaps in yield curve data"""

    MAX_GAP_DAYS = 7  # Warn if missing more than 7 days

    def __init__(self):
        super().__init__(
            rule_code='RULE_YC_DAY_GAP',
            name='Yield Curve Data Gap Detection',
            description=f'WARN if missing data for more than {self.MAX_GAP_DAYS} consecutive days'
        )

    def check(self, db_manager, target_date: date) -> Tuple[bool, str, str, Dict[str, Any]]:
        try:
            # Get recent yield curve dates
            sql = """
            SELECT DISTINCT date
            FROM gov_yield_curve
            WHERE date <= ?
            ORDER BY date DESC
            LIMIT 30
            """

            results = db_manager.con.execute(sql, [str(target_date)]).fetchall()

            if not results:
                return False, 'ERROR', 'No yield curve data found in last 30 days', {}

            dates = [row[0] for row in results]
            latest_date = dates[0]

            if latest_date < target_date - timedelta(days=self.MAX_GAP_DAYS):
                gap_days = (target_date - latest_date).days
                return False, 'WARN', f'Gap of {gap_days} days since last yield curve data (latest: {latest_date})', {
                    'latest_date': str(latest_date),
                    'target_date': str(target_date),
                    'gap_days': gap_days
                }

            return True, 'INFO', f'No significant data gaps (latest: {latest_date})', {
                'latest_date': str(latest_date)
            }

        except Exception as e:
            logger.error(f"Error checking yield curve day gap: {e}")
            return False, 'ERROR', f'Rule execution failed: {str(e)}', {'error': str(e)}


class InterbankTenorCoverage(DataQualityRule):
    """Check if ON (overnight) rate is present"""

    def __init__(self):
        super().__init__(
            rule_code='RULE_IB_TENOR_COVERAGE',
            name='Interbank Rate Tenor Coverage',
            description='Checks if ON (overnight) rate is present'
        )

    def check(self, db_manager, target_date: date) -> Tuple[bool, str, str, Dict[str, Any]]:
        try:
            ib_data = db_manager.get_interbank_rates(str(target_date), str(target_date))
            used_date = target_date
            gap_days = 0

            if not ib_data:
                # SBV publishes an "applied date" which can lag the run date (weekends/holidays).
                # Treat missing exact-date data as WARN and fall back to the latest available <= target_date.
                latest = db_manager.con.execute(
                    "SELECT MAX(date) FROM interbank_rates WHERE date <= ?",
                    [str(target_date)],
                ).fetchone()
                latest_date = latest[0] if latest else None
                if not latest_date:
                    return False, "WARN", "No interbank rate data found", {}

                used_date = latest_date
                try:
                    gap_days = (target_date - latest_date).days
                except Exception:
                    gap_days = None

                ib_data = db_manager.get_interbank_rates(str(latest_date), str(latest_date))
                if not ib_data:
                    return False, "WARN", "No interbank rate data found", {}

            has_on = any(row.get('tenor_label') == 'ON' for row in ib_data)

            if not has_on:
                return False, 'WARN', 'Missing ON (overnight) rate', {
                    'available_tenors': [row.get('tenor_label') for row in ib_data if row.get('tenor_label')],
                    'used_date': str(used_date),
                    'gap_days': gap_days,
                }

            return True, 'INFO', 'ON rate present', {
                'on_rate': next((row.get('rate') for row in ib_data if row.get('tenor_label') == 'ON'), None),
                'used_date': str(used_date),
                'gap_days': gap_days,
            }

        except Exception as e:
            logger.error(f"Error checking interbank tenor coverage: {e}")
            return False, 'ERROR', f'Rule execution failed: {str(e)}', {'error': str(e)}


class InterbankRangeSanity(DataQualityRule):
    """Check if interbank rates are within reasonable bounds"""

    MIN_RATE = -1.0  # -1%
    MAX_RATE = 30.0  # 30%

    def __init__(self):
        super().__init__(
            rule_code='RULE_IB_RANGE_SANITY',
            name='Interbank Rate Range Sanity',
            description=f'Checks if rates are between {self.MIN_RATE}% and {self.MAX_RATE}%'
        )

    def check(self, db_manager, target_date: date) -> Tuple[bool, str, str, Dict[str, Any]]:
        try:
            ib_data = db_manager.get_interbank_rates(str(target_date), str(target_date))

            if not ib_data:
                return True, 'INFO', 'No interbank rate data to check', {}

            out_of_range = []
            for row in ib_data:
                rate = row.get('rate')
                if rate is not None:
                    if rate < self.MIN_RATE or rate > self.MAX_RATE:
                        out_of_range.append({
                            'tenor': row.get('tenor_label'),
                            'rate': rate
                        })

            if out_of_range:
                return False, 'ERROR', f'Rates outside valid range: {out_of_range}', {
                    'out_of_range': out_of_range
                }

            return True, 'INFO', 'All rates within valid range', {
                'checked_count': len(ib_data)
            }

        except Exception as e:
            logger.error(f"Error checking interbank rate range: {e}")
            return False, 'ERROR', f'Rule execution failed: {str(e)}', {'error': str(e)}


class InterbankSpikeSanity(DataQualityRule):
    """Check for unusual day-over-day spikes in interbank rates"""

    MAX_SPIKE_BPS = 200  # 200 basis points = 2%

    def __init__(self):
        super().__init__(
            rule_code='RULE_IB_SPIKE_SANITY',
            name='Interbank Rate Spike Detection',
            description=f'WARN if day-over-day change exceeds {self.MAX_SPIKE_BPS} bps'
        )

    def check(self, db_manager, target_date: date) -> Tuple[bool, str, str, Dict[str, Any]]:
        try:
            # Get current and previous day rates
            current_data = db_manager.get_interbank_rates(str(target_date), str(target_date))
            prev_date = target_date - timedelta(days=1)
            prev_data = db_manager.get_interbank_rates(str(prev_date), str(prev_date))

            if not current_data or not prev_data:
                return True, 'INFO', 'Insufficient data to check spikes', {}

            # Build dictionaries
            current_rates = {row.get('tenor_label'): row.get('rate') for row in current_data if row.get('rate') is not None}
            prev_rates = {row.get('tenor_label'): row.get('rate') for row in prev_data if row.get('rate') is not None}

            spikes = []
            for tenor in current_rates:
                if tenor and tenor in prev_rates:
                    change_bps = (current_rates[tenor] - prev_rates[tenor]) * 100
                    if abs(change_bps) > self.MAX_SPIKE_BPS:
                        spikes.append({
                            'tenor': tenor,
                            'change_bps': change_bps,
                            'prev_rate': prev_rates[tenor],
                            'current_rate': current_rates[tenor]
                        })

            if spikes:
                return False, 'WARN', f'Large rate spikes detected: {spikes}', {
                    'spikes': spikes,
                    'threshold_bps': self.MAX_SPIKE_BPS
                }

            return True, 'INFO', 'No unusual rate spikes', {}

        except Exception as e:
            logger.error(f"Error checking interbank rate spikes: {e}")
            return False, 'ERROR', f'Rule execution failed: {str(e)}', {'error': str(e)}


class NumericParseCheck(DataQualityRule):
    """Check that numeric fields are properly parsed (no NaN)"""

    def __init__(self, table_name: str, numeric_fields: List[str]):
        super().__init__(
            rule_code=f'RULE_NUMERIC_PARSE_{table_name.upper()}',
            name=f'Numeric Parse Check - {table_name}',
            description=f'Checks that numeric fields in {table_name} are not NaN or invalid'
        )
        self.table_name = table_name
        self.numeric_fields = numeric_fields

    def check(self, db_manager, target_date: date) -> Tuple[bool, str, str, Dict[str, Any]]:
        try:
            # Build dynamic SQL to check for NaN in key numeric fields.
            # Note: NULL is allowed for optional fields.
            conditions = []
            for field in self.numeric_fields:
                conditions.append(f"({field} != {field})")  # NaN check

            sql = f"""
            SELECT COUNT(*) as invalid_count
            FROM {self.table_name}
            WHERE date = ? AND ({' OR '.join(conditions)})
            """

            result = db_manager.con.execute(sql, [str(target_date)]).fetchone()

            if result and result[0] > 0:
                return False, 'WARN', f'Found {result[0]} records with invalid numeric values', {
                    'invalid_count': result[0],
                    'checked_fields': self.numeric_fields
                }

            return True, 'INFO', 'All numeric fields valid', {
                'checked_fields': self.numeric_fields
            }

        except Exception as e:
            logger.error(f"Error checking numeric parse for {self.table_name}: {e}")
            return False, 'ERROR', f'Rule execution failed: {str(e)}', {'error': str(e)}


class NegativeValuesCheck(DataQualityRule):
    """Check that volume/value fields are non-negative"""

    def __init__(self, table_name: str, non_negative_fields: List[str]):
        super().__init__(
            rule_code=f'RULE_NEGATIVE_VALUES_{table_name.upper()}',
            name=f'Negative Values Check - {table_name}',
            description=f'Checks that volume/value fields in {table_name} are >= 0'
        )
        self.table_name = table_name
        self.non_negative_fields = non_negative_fields

    def check(self, db_manager, target_date: date) -> Tuple[bool, str, str, Dict[str, Any]]:
        try:
            # Build dynamic SQL to check for negative values
            conditions = []
            for field in self.non_negative_fields:
                conditions.append(f"{field} < 0")

            sql = f"""
            SELECT COUNT(*) as negative_count
            FROM {self.table_name}
            WHERE date = ? AND ({' OR '.join(conditions)})
            """

            result = db_manager.con.execute(sql, [str(target_date)]).fetchone()

            if result and result[0] > 0:
                return False, 'ERROR', f'Found {result[0]} records with negative values', {
                    'negative_count': result[0],
                    'checked_fields': self.non_negative_fields
                }

            return True, 'INFO', 'All volume/value fields are non-negative', {
                'checked_fields': self.non_negative_fields
            }

        except Exception as e:
            logger.error(f"Error checking negative values for {self.table_name}: {e}")
            return False, 'ERROR', f'Rule execution failed: {str(e)}', {'error': str(e)}


# Registry of rules per dataset
DATASET_RULES = {
    'gov_yield_curve': [
        YieldCurveTenorCoverage(),
        YieldCurveRangeSanity(),
        YieldCurveDayGap()
    ],
    'interbank_rates': [
        InterbankTenorCoverage(),
        InterbankRangeSanity(),
        InterbankSpikeSanity()
    ],
    'gov_auction_results': [
        NumericParseCheck('gov_auction_results', ['amount_offered', 'amount_sold', 'bid_to_cover', 'cut_off_yield', 'avg_yield']),
        NegativeValuesCheck('gov_auction_results', ['amount_offered', 'amount_sold', 'bid_to_cover'])
    ],
    'gov_secondary_trading': [
        NumericParseCheck('gov_secondary_trading', ['value', 'volume', 'avg_yield']),
        NegativeValuesCheck('gov_secondary_trading', ['value', 'volume'])
    ],
    'policy_rates': [
        NumericParseCheck('policy_rates', ['rate']),
        NegativeValuesCheck('policy_rates', ['rate'])
    ]
}


def get_rules_for_dataset(dataset_id: str) -> List[DataQualityRule]:
    """Get all applicable rules for a dataset"""
    return DATASET_RULES.get(dataset_id, [])


def get_all_datasets() -> List[str]:
    """Get list of all datasets with DQ rules"""
    return list(DATASET_RULES.keys())


class SourceDriftDetection(DataQualityRule):
    """Check for source content drift (fingerprint changes)"""

    def __init__(self, provider: str, dataset_id: str):
        super().__init__(
            rule_code='RULE_SOURCE_DRIFT',
            name=f'Source Drift Detection - {provider}/{dataset_id}',
            description=f'Detects when upstream source content changes for {provider}/{dataset_id}'
        )
        self.provider = provider
        self.dataset_id = dataset_id

    def check(self, db_manager, target_date: date) -> Tuple[bool, str, str, Dict[str, Any]]:
        try:
            # Get latest fingerprint for this provider/dataset
            sql = """
            SELECT fingerprint_hash, parse_rowcount, parse_required_fields_ok,
                   target_date, fetched_at, note
            FROM source_fingerprints
            WHERE provider = ? AND dataset_id = ? AND target_date <= ?
            ORDER BY fetched_at DESC, id DESC
            LIMIT 2
            """

            results = db_manager.con.execute(sql, [self.provider, self.dataset_id, str(target_date)]).fetchall()

            if not results:
                return True, 'INFO', 'No fingerprints recorded yet (first fetch)', {}

            if len(results) == 1:
                return True, 'INFO', 'First fingerprint recorded', {
                    'fingerprint': results[0][0][:16] + '...'
                }

            # Check for drift
            latest = results[0]
            previous = results[1]

            if latest[0] != previous[0]:
                drift_info = {
                    'latest_fingerprint': latest[0][:16] + '...',
                    'previous_fingerprint': previous[0][:16] + '...'
                }

                # Check for regression
                if latest[1] is not None and previous[1] is not None:
                    rowcount_change = latest[1] - previous[1]
                    if rowcount_change < -0.1 * previous[1]:
                        return False, 'ERROR', f'Source drift with regression', {
                            **drift_info,
                            'regression': True
                        }

                return False, 'WARN', 'Source content changed', drift_info

            return True, 'INFO', 'No source drift', {}

        except Exception as e:
            logger.error(f"Error checking source drift: {e}")
            return False, 'ERROR', f'Rule execution failed: {str(e)}', {}
