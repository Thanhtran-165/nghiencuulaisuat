"""
Base provider class for all data providers
"""
import httpx
import logging
import certifi
import ssl
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app import config


logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Base exception for provider errors"""
    pass


class RateLimitError(ProviderError):
    """Raised when rate limit is hit"""
    pass


class ParseError(ProviderError):
    """Raised when parsing fails"""
    pass


class NotSupportedError(ProviderError):
    """Raised when a provider doesn't support a requested operation"""
    pass


class BaseProvider:
    """Base class for all data providers"""

    def __init__(self):
        self.name = self.__class__.__name__
        verify: str | ssl.SSLContext | bool
        try:
            import truststore

            truststore.inject_into_ssl()
            verify = True
        except Exception:
            verify = certifi.where()

        self.client = httpx.Client(
            timeout=config.settings.request_timeout,
            follow_redirects=True,
            verify=verify,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()

    def fetch(self, target_date: date) -> List[Dict[str, Any]]:
        """
        Fetch data for a specific date

        Args:
            target_date: The date to fetch data for

        Returns:
            List of dictionaries containing the data
        """
        raise NotSupportedError(f"{self.name} does not implement fetch()")

    def backfill(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        Backfill data for a date range

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of dictionaries containing the data
        """
        raise NotSupportedError(f"{self.name} does not support backfill()")

    @retry(
        stop=stop_after_attempt(config.settings.max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, RateLimitError))
    )
    def _get(self, url: str, **kwargs) -> httpx.Response:
        """
        Make HTTP GET request with retry logic

        Args:
            url: URL to fetch
            **kwargs: Additional arguments for httpx.get

        Returns:
            httpx.Response object
        """
        try:
            response = self.client.get(url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning(f"Rate limit hit for {url}")
                raise RateLimitError(f"Rate limit hit: {url}")
            raise
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching {url}: {e}")
            raise

    @retry(
        stop=stop_after_attempt(config.settings.max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, RateLimitError))
    )
    def _post(self, url: str, **kwargs) -> httpx.Response:
        """
        Make HTTP POST request with retry logic

        Args:
            url: URL to post to
            **kwargs: Additional arguments for httpx.post

        Returns:
            httpx.Response object
        """
        try:
            response = self.client.post(url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning(f"Rate limit hit for {url}")
                raise RateLimitError(f"Rate limit hit: {url}")
            raise
        except httpx.HTTPError as e:
            logger.error(f"HTTP error posting {url}: {e}")
            raise

    def _save_raw(self, filename: str, content: bytes) -> Optional[Path]:
        """
        Save raw content to disk if enabled

        Args:
            filename: Name of the file
            content: Content to save

        Returns:
            Path to saved file or None if storage is disabled
        """
        # Access config dynamically to support test-time reloads.
        if not config.settings.enable_raw_storage:
            return None

        try:
            raw_path = config.get_raw_data_path(self.name)
            file_path = raw_path / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, 'wb') as f:
                f.write(content)

            logger.debug(f"Saved raw data to {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Failed to save raw data: {e}")
            return None

    def _parse_vietnamese_float(self, value: str) -> Optional[float]:
        """
        Parse Vietnamese float format (comma as decimal separator)

        Args:
            value: String value to parse

        Returns:
            Parsed float or None if parsing fails
        """
        if not value or value.strip() in ['', '-', 'N/A', 'NA']:
            return None

        try:
            import re

            cleaned = value.strip().replace('%', '').strip()

            # Vietnamese convention: '.' thousands separator, ',' decimal separator.
            # If a comma is present, treat it as the decimal separator and strip any thousands dots.
            if ',' in cleaned:
                cleaned = cleaned.replace('.', '')
                cleaned = cleaned.replace(',', '.')
                return float(cleaned)

            # If only dots exist, it may be either a decimal point or thousands separators.
            # Treat patterns like 1.234.567 as thousands separators, otherwise keep dot as decimal.
            if re.fullmatch(r'\d{1,3}(?:\.\d{3})+', cleaned):
                cleaned = cleaned.replace('.', '')

            return float(cleaned)
        except (ValueError, AttributeError):
            logger.debug(f"Failed to parse float: {value}")
            return None

    def _parse_vietnamese_int(self, value: str) -> Optional[int]:
        """
        Parse Vietnamese integer format

        Args:
            value: String value to parse

        Returns:
            Parsed int or None if parsing fails
        """
        float_val = self._parse_vietnamese_float(value)
        return int(float_val) if float_val is not None else None

    def _standardize_date(self, date_str: str, formats: List[str]) -> Optional[date]:
        """
        Try to parse date string using multiple formats

        Args:
            date_str: Date string to parse
            formats: List of date format strings to try

        Returns:
            Parsed date or None if all formats fail
        """
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue
        logger.warning(f"Failed to parse date: {date_str}")
        return None
