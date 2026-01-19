"""
FRED (Federal Reserve Economic Data) Global Data Provider
Fetches US and global market indicators for comparison with VN bond market

Requires: requests library
Optional: FRED_API_KEY environment variable (free from https://fred.stlouisfed.org/docs/api/api_key.html)
Without API key: Limited functionality with clear error messages
"""
import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class FREDGlobalProvider:
    """
    FRED Global Data Provider

    Fetches US Treasury yields, volatility indices, and FX rates for comparison
    with Vietnamese bond market data.

    Free API key available from: https://fred.stlouisfed.org/docs/api/api_key.html
    """

    # Default series to fetch (minimal high-value set)
    DEFAULT_SERIES = {
        'DGS10': 'US 10-Year Treasury Constant Maturity Rate',
        'DGS2': 'US 2-Year Treasury Constant Maturity Rate',
        'DGS3MO': 'US 3-Month Treasury Constant Maturity Rate',
        'VIXCLS': 'CBOE Volatility Index: VIX',
        'SOFR': 'Secured Overnight Financing Rate',
        'DTWEXBGS': 'Trade Weighted U.S. Dollar Index: Broad'
    }

    # Provider metadata
    provider_name = 'fred_global'
    provider_type = 'global_rates'
    supports_historical = True  # If API key provided
    backfill_supported = True
    earliest_success_date = None  # Will be set dynamically
    latest_success_date = None  # Will be set dynamically

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize FRED provider

        Args:
            api_key: FRED API key (optional, recommended). Get free from:
                    https://fred.stlouisfed.org/docs/api/api_key.html
        """
        self.api_key = api_key or getattr(settings, 'fred_api_key', None)
        self.base_url = "https://api.stlouisfed.org/fred/series/observations"

        if not self.api_key:
            logger.warning("FRED API key not provided. Set FRED_API_KEY in .env for full functionality.")
            self.supports_historical = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def fetch(self, target_date) -> List[Dict[str, Any]]:
        """
        Pipeline-compatible fetch() wrapper.

        Note: FRED series publish on business days; we fetch the latest observation
        available around the target_date.
        """
        return self.fetch_latest()

    def backfill(self, start_date, end_date) -> List[Dict[str, Any]]:
        """Pipeline-compatible backfill() wrapper."""
        return self.fetch_range(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))

    def fetch_latest(self) -> List[Dict[str, Any]]:
        """
        Fetch latest available data points for all configured series

        Returns:
            List of records in standard format
        """
        if not self.api_key:
            logger.error("Cannot fetch FRED data without API key")
            return []

        logger.info("Fetching latest FRED global data")

        records = []
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=7)  # Last 7 days to ensure we get latest

        for series_id, series_name in self.DEFAULT_SERIES.items():
            try:
                data = self._fetch_series_range(series_id, series_name, start_date, end_date)

                # Get only the latest observation
                if data:
                    latest = max(data, key=lambda x: x['date'])
                    records.append(latest)
                    logger.debug(f"Fetched {series_id}: {latest['date']} = {latest['value']}")

            except Exception as e:
                logger.warning(f"Failed to fetch {series_id}: {e}")
                continue

        logger.info(f"Fetched {len(records)} latest FRED observations")
        return records

    def fetch_range(
        self,
        start_date: str,
        end_date: str,
        series_ids: Optional[List[str]] = None,
        chunk_size: int = 90
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical data for a date range

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            series_ids: List of series IDs to fetch (default: all default series)
            chunk_size: Days per chunk (FRED limits, default 90 days)

        Returns:
            List of records in standard format
        """
        if not self.api_key:
            logger.error("Cannot fetch FRED historical data without API key")
            return []

        logger.info(f"Fetching FRED data from {start_date} to {end_date}")

        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()

        if series_ids is None:
            series_ids = list(self.DEFAULT_SERIES.keys())

        all_records = []
        current_start = start

        # Fetch in chunks to respect API limits
        while current_start <= end:
            current_end = min(current_start + timedelta(days=chunk_size), end)

            logger.info(f"Fetching chunk: {current_start} to {current_end}")

            for series_id in series_ids:
                if series_id not in self.DEFAULT_SERIES:
                    logger.warning(f"Unknown series ID: {series_id}")
                    continue

                series_name = self.DEFAULT_SERIES[series_id]

                try:
                    records = self._fetch_series_range(
                        series_id,
                        series_name,
                        current_start,
                        current_end
                    )
                    all_records.extend(records)

                except Exception as e:
                    logger.warning(f"Failed to fetch {series_id} for chunk {current_start}: {e}")
                    continue

            current_start = current_end + timedelta(days=1)

        logger.info(f"Fetched {len(all_records)} total FRED observations")
        return all_records

    def _fetch_series_range(
        self,
        series_id: str,
        series_name: str,
        start_date,
        end_date
    ) -> List[Dict[str, Any]]:
        """
        Fetch data for a specific series and date range

        Args:
            series_id: FRED series ID
            series_name: Human-readable series name
            start_date: Start date object
            end_date: End date object

        Returns:
            List of records
        """
        params = {
            'series_id': series_id,
            'api_key': self.api_key,
            'file_type': 'json',
            'observation_start': start_date.strftime('%Y-%m-%d'),
            'observation_end': end_date.strftime('%Y-%m-%d')
        }

        try:
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()

            if data.get('error_code'):
                logger.error(f"FRED API error: {data.get('error_message', 'Unknown error')}")
                return []

            observations = data.get('observations', [])

            records = []
            for obs in observations:
                # Skip missing values (represented as '.' by FRED)
                if obs.get('value') == '.':
                    continue

                try:
                    records.append({
                        'date': datetime.strptime(obs['date'], '%Y-%m-%d').date(),
                        'series_id': series_id,
                        'series_name': series_name,
                        'value': float(obs['value']),
                        'source': 'FRED',
                        'fetched_at': datetime.now().isoformat()
                    })
                except (ValueError, KeyError) as e:
                    logger.debug(f"Skipping invalid observation: {e}")
                    continue

            return records

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP error fetching {series_id}: {e}")
            return []

    def get_available_series(self) -> Dict[str, str]:
        """Return mapping of available series IDs to names"""
        return self.DEFAULT_SERIES.copy()

    def check_connection(self) -> bool:
        """
        Check if FRED API is accessible

        Returns:
            True if API key is valid and connection works
        """
        if not self.api_key:
            return False

        try:
            # Try to fetch one recent observation
            params = {
                'series_id': 'DGS10',
                'api_key': self.api_key,
                'file_type': 'json',
                'limit': 1
            }

            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            return data.get('error_code') != 400  # 400 = invalid API key

        except Exception as e:
            logger.warning(f"FRED connection check failed: {e}")
            return False


# For backwards compatibility
HNXYieldCurveProvider = FREDGlobalProvider
