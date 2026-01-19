"""Scraper module for fetching and parsing bank rate data."""

import requests
from typing import Dict, Any, List, Tuple
from .parsers.deposit import DepositParser
from .parsers.loan import LoanParser
from .parsers.deposit_24hmoney import parse_deposit_24hmoney
from .utils import get_utc_timestamp, logger


class Scraper:
    """Scraper for fetching and parsing bank rate data."""

    # Timo sources
    TIMO_DEPOSIT_URL = "https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/"
    TIMO_LOAN_URL = "https://timo.vn/blogs/so-sanh-lai-suat-vay-ngan-hang-cap-nhat-moi-nhat/"

    # 24hmoney source
    H24MONEY_DEPOSIT_URL = "https://24hmoney.vn/lai-suat-gui-ngan-hang"

    # Backwards-compatible aliases used by scrape_deposit/scrape_loan.
    DEPOSIT_URL = TIMO_DEPOSIT_URL
    LOAN_URL = TIMO_LOAN_URL

    def __init__(self, timeout: int = 30):
        """
        Initialize scraper.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

    def fetch_url(self, url: str) -> Tuple[str, int, str]:
        """
        Fetch HTML content from URL.

        Args:
            url: URL to fetch

        Returns:
            Tuple of (html_content, http_status, fetched_at)

        Raises:
            requests.RequestException: If fetch fails
        """
        logger.info(f"Fetching URL: {url}")
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        response.encoding = 'utf-8'
        fetched_at = get_utc_timestamp()
        return response.text, response.status_code, fetched_at

    def scrape_deposit(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Scrape deposit interest rates.

        Returns:
            Tuple of (records, metadata)
        """
        html_content, http_status, fetched_at = self.fetch_url(self.DEPOSIT_URL)
        scraped_at = get_utc_timestamp()

        parser = DepositParser(html_content, self.DEPOSIT_URL, scraped_at)
        records, parse_metadata = parser.parse()

        # Extract page metadata
        page_metadata = parser.extract_metadata()
        metadata = {
            'url': self.DEPOSIT_URL,
            'scraped_at': scraped_at,
            'parse_metadata': parse_metadata,
            'page_metadata': page_metadata,
            'http_status': http_status,
            'fetched_at': fetched_at,
            'html_content': html_content  # Cache for ingest
        }

        return records, metadata

    def scrape_loan(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Scrape loan interest rates.

        Returns:
            Tuple of (records, metadata)
        """
        html_content, http_status, fetched_at = self.fetch_url(self.LOAN_URL)
        scraped_at = get_utc_timestamp()

        parser = LoanParser(html_content, self.LOAN_URL, scraped_at)
        records, parse_metadata = parser.parse()

        # Extract page metadata
        page_metadata = parser.extract_metadata()
        metadata = {
            'url': self.LOAN_URL,
            'scraped_at': scraped_at,
            'parse_metadata': parse_metadata,
            'page_metadata': page_metadata,
            'http_status': http_status,
            'fetched_at': fetched_at,
            'html_content': html_content  # Cache for ingest
        }

        return records, metadata

    def scrape_all(self) -> Dict[str, Tuple[List[Dict[str, Any]], Dict[str, Any]]]:
        """
        Scrape all URLs.

        Returns:
            Dictionary with source_id keys, each containing
            (records, metadata) tuple
        """
        results = {}

        # Scrape Timo deposit
        try:
            results['timo_deposit'] = self.scrape_timo_deposit()
        except Exception as e:
            logger.error(f"Failed to scrape timo_deposit: {e}")
            results['timo_deposit'] = ([], {'error': str(e)})

        # Scrape 24hmoney deposit
        try:
            results['24hmoney_deposit'] = self.scrape_24hmoney_deposit()
        except Exception as e:
            logger.error(f"Failed to scrape 24hmoney_deposit: {e}")
            results['24hmoney_deposit'] = ([], {'error': str(e)})

        # Scrape Timo loan
        try:
            results['timo_loan'] = self.scrape_timo_loan()
        except Exception as e:
            logger.error(f"Failed to scrape timo_loan: {e}")
            results['timo_loan'] = ([], {'error': str(e)})

        return results

    def scrape_timo_deposit(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Scrape Timo deposit interest rates.

        Returns:
            Tuple of (records, metadata)
        """
        html_content, http_status, fetched_at = self.fetch_url(self.TIMO_DEPOSIT_URL)
        scraped_at = get_utc_timestamp()

        parser = DepositParser(html_content, self.TIMO_DEPOSIT_URL, scraped_at)
        records, parse_metadata = parser.parse()

        # Extract page metadata
        page_metadata = parser.extract_metadata()
        metadata = {
            'url': self.TIMO_DEPOSIT_URL,
            'scraped_at': scraped_at,
            'parse_metadata': parse_metadata,
            'page_metadata': page_metadata,
            'http_status': http_status,
            'fetched_at': fetched_at,
            'html_content': html_content  # Cache for ingest
        }

        return records, metadata

    def scrape_timo_loan(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Scrape Timo loan interest rates.

        Returns:
            Tuple of (records, metadata)
        """
        html_content, http_status, fetched_at = self.fetch_url(self.TIMO_LOAN_URL)
        scraped_at = get_utc_timestamp()

        parser = LoanParser(html_content, self.TIMO_LOAN_URL, scraped_at)
        records, parse_metadata = parser.parse()

        # Extract page metadata
        page_metadata = parser.extract_metadata()
        metadata = {
            'url': self.TIMO_LOAN_URL,
            'scraped_at': scraped_at,
            'parse_metadata': parse_metadata,
            'page_metadata': page_metadata,
            'http_status': http_status,
            'fetched_at': fetched_at,
            'html_content': html_content  # Cache for ingest
        }

        return records, metadata

    def scrape_24hmoney_deposit(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Scrape 24hmoney deposit interest rates (includes both online and offline).

        Returns:
            Tuple of (records, metadata)
        """
        html_content, http_status, fetched_at = self.fetch_url(self.H24MONEY_DEPOSIT_URL)
        scraped_at = get_utc_timestamp()

        # Use 24hmoney parser
        records, parse_metadata = parse_deposit_24hmoney(html_content, self.H24MONEY_DEPOSIT_URL, scraped_at)

        metadata = {
            'url': self.H24MONEY_DEPOSIT_URL,
            'scraped_at': scraped_at,
            'parse_metadata': parse_metadata,
            'page_metadata': {'page_updated_text': None},  # Not extracted by this parser
            'http_status': http_status,
            'fetched_at': fetched_at,
            'html_content': html_content  # Cache for ingest
        }

        return records, metadata
