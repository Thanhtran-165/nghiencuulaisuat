"""
SBV Interbank Rates Provider
Fetches interbank interest rates from State Bank of Vietnam

Historical Access Verdict: LATEST ONLY (official)
- SBV interbank rate page does not expose date range parameters in public interface
- Only the latest rates are available via official SBV portal
- Historical backfill is NOT supported
- Daily snapshot accumulation is used with ABO as fallback/validation
"""
import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import re

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from app.providers.base import BaseProvider, ProviderError, ParseError, NotSupportedError
from app.config import settings

logger = logging.getLogger(__name__)


class SBVInterbankProvider(BaseProvider):
    """
    Provider for SBV Interbank Interest Rates

    Source: https://www.sbv.gov.vn/webcenter/portal/m/menu/trangchu/ls/lsttlnh

    Capability Flags:
    - supports_historical: False (no date range parameters in public interface)
    - supports_yesterday: False (only latest available)
    - supports_range_backfill: False (returns latest only)

    Strategy:
    - Primary: Daily snapshot accumulation from official SBV portal
    - Secondary: ABO VNIBOR for validation/fallback (marked as non-official)
    """

    # Tenor mappings
    TENOR_MAP = {
        'ON': ('ON', 0),
        '1W': ('1W', 7),
        '2W': ('2W', 14),
        '1M': ('1M', 30),
        '3M': ('3M', 90),
        '6M': ('6M', 180),
        '9M': ('9M', 270),
        '12M': ('12M', 365),
    }

    VIETNAMESE_TENORS = {
        'qua đêm': ('ON', 0),
        '1 tuần': ('1W', 7),
        '2 tuần': ('2W', 14),
        '1 tháng': ('1M', 30),
        '3 tháng': ('3M', 90),
        '6 tháng': ('6M', 180),
        '9 tháng': ('9M', 270),
        '12 tháng': ('12M', 365),
    }

    DATE_FORMATS = [
        '%d/%m/%Y',
        '%Y-%m-%d',
        '%d-%m-%Y',
    ]

    def __init__(self):
        super().__init__()
        # The legacy portal URL frequently redirects and may not be reachable in some networks.
        # SBV publishes both policy rates and interbank market rates on the public "Lãi suất" page.
        self.interbank_url = f"{settings.sbv_base_url}/l%C3%A3i-su%E1%BA%A5t1"

        # Capability flags (determined by inspection)
        self.supports_historical = False
        self.supports_yesterday = False
        self.supports_range_backfill = False

    def fetch(self, target_date: date) -> List[Dict[str, Any]]:
        """
        Fetch interbank rates for a specific date

        Note: This provider only supports fetching the latest rates.
        The target_date parameter is used for the record date field,
        but the actual data fetched will be the latest available.

        Args:
            target_date: Date to use for record labeling (data will be latest)

        Returns:
            List of interbank rate records (latest available, labeled with target_date)
        """
        logger.info(f"Fetching SBV interbank rates (latest only) for {target_date}")

        # Warn if trying to fetch non-latest data
        if target_date != date.today():
            logger.warning(
                f"SBV interbank rates only support latest data. "
                f"Requested {target_date} but will fetch latest. "
                f"Record will be labeled with {target_date}."
            )

        try:
            records = self._fetch_http(target_date)

            if not records:
                logger.warning(f"No interbank rate data found for {target_date}")
                return []

            logger.info(f"Found {len(records)} interbank rate records for {target_date}")
            return records

        except Exception as e:
            logger.error(f"Error fetching interbank rates for {target_date}: {e}")
            raise ProviderError(f"Failed to fetch interbank rates: {e}")

    def backfill(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        Backfill interbank rates for a date range

        NOT SUPPORTED: SBV interbank rates do not support historical access.
        This method raises NotSupportedError.

        For daily snapshot accumulation, use fetch() in a daily job.
        Records will accumulate over time from your start date.

        Use AsianBondsOnline (ABO) as fallback for historical validation.

        Args:
            start_date: Start date (ignored, not supported)
            end_date: End date (ignored, not supported)

        Raises:
            NotSupportedError: Always - historical backfill not available

        """
        raise NotSupportedError(
            "SBV interbank rates do not support historical backfill. "
            "The public interface only provides the latest rates. "
            "Use daily snapshot accumulation: run 'python -m app.ingest daily' "
            "to accumulate data from your start date. "
            "For historical validation, use AsianBondsOnline (ABO) as fallback."
        )

    def discover_endpoints(self) -> Dict[str, Any]:
        """
        Use Playwright to discover if there are any date range parameters
        or API endpoints that support historical data access.

        Returns:
            Dictionary with discovery results
        """
        logger.info("Running SBV endpoint discovery...")

        discovery_result = {
            'provider': 'SBVInterbankProvider',
            'url': self.interbank_url,
            'has_date_range_params': False,
            'has_date_picker': False,
            'has_api_endpoint': False,
            'api_endpoints_found': [],
            'recommendation': 'latest_only'
        }

        if not PLAYWRIGHT_AVAILABLE:
            discovery_result['discovery_error'] = 'Playwright not available'
            return discovery_result

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=settings.playwright_headless)
                page = browser.new_page()

                # Track network requests
                api_endpoints = []

                def handle_request(request):
                    url = request.url
                    # Look for API endpoints with potential date parameters
                    if '/api/' in url.lower() or 'ajax' in url.lower():
                        api_endpoints.append({
                            'url': url,
                            'method': request.method,
                            'resource_type': request.resource_type,
                            'has_date_param': any(keyword in url.lower() for keyword in ['date', 'from', 'to', 'start', 'end'])
                        })

                page.on('request', handle_request)

                # Navigate to interbank rates page
                logger.info(f"Navigating to {self.interbank_url}")
                page.goto(self.interbank_url, timeout=settings.playwright_timeout)

                # Wait for content to load
                page.wait_for_load_state('networkidle', timeout=10000)

                # Check for date range inputs
                date_inputs = page.query_selector_all(
                    'input[type="date"], input[name*="date"], input[id*="date"], '
                    'input[placeholder*="từ"], input[placeholder*="đến"]'
                )
                has_date_picker = len(date_inputs) > 0

                # Check for form submissions with date parameters
                forms = page.query_selector_all('form')
                date_forms = []
                for form in forms:
                    form_html = form.evaluate('el => el.outerHTML')
                    if any(keyword in form_html.lower() for keyword in ['date', 'từ ngày', 'đến ngày']):
                        date_forms.append(form_html[:200])

                browser.close()

                # Update discovery results
                discovery_result['has_date_range_params'] = len(date_inputs) > 0 or len(date_forms) > 0
                discovery_result['has_date_picker'] = has_date_picker
                discovery_result['api_endpoints_found'] = api_endpoints

                # Determine if any API endpoint has date parameters
                if api_endpoints:
                    for endpoint in api_endpoints:
                        if endpoint['has_date_param']:
                            discovery_result['has_api_endpoint'] = True
                            discovery_result['recommendation'] = 'historical_possible'
                            break

                if discovery_result['recommendation'] == 'latest_only':
                    logger.info("Discovery complete: latest only (no date range parameters found)")
                else:
                    logger.info("Discovery complete: historical access possible")

                return discovery_result

        except Exception as e:
            logger.error(f"Error during endpoint discovery: {e}")
            discovery_result['discovery_error'] = str(e)
            return discovery_result

    def _fetch_http(self, target_date: date) -> List[Dict[str, Any]]:
        """Fetch using direct HTTP request"""
        try:
            response = self._get(self.interbank_url)
            self._save_raw(f"interbank_{target_date.strftime('%Y%m%d')}.html", response.content)

            soup = BeautifulSoup(response.content, 'html.parser')
            return self._parse_interbank_market_table(soup)

        except Exception as e:
            logger.debug(f"HTTP fetch failed: {e}")
            return []

    def _parse_interbank_market_table(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Parse SBV interbank market rates from the public SBV "Lãi suất" page.

        Expected structure:
          - <h3>...Lãi suất thị trường liên ngân hàng...</h3>
          - a sibling table with columns: Thời hạn, Lãi suất..., Doanh số...
        """
        records: list[dict] = []

        # Locate the interbank section by its heading text.
        heading = soup.find(lambda tag: tag.name in ("h2", "h3") and "liên ngân hàng" in tag.get_text(" ", strip=True).lower())
        if heading is None:
            return []

        container = heading.find_parent()
        if container is None:
            return []

        # Applied date is shown in a sibling "Ngày áp dụng: <strong>..</strong>"
        applied_date = None
        subnote = container.find(lambda tag: tag.name in ("div", "p") and "ngày áp dụng" in tag.get_text(" ", strip=True).lower())
        if subnote is not None:
            strong = subnote.find("strong")
            if strong:
                applied_date = self._standardize_date(strong.get_text(strip=True), self.DATE_FORMATS)

        table = container.find("table")
        if table is None:
            return []

        for row in table.find_all("tr"):
            tds = row.find_all("td")
            if len(tds) < 2:
                continue

            tenor_text = tds[0].get_text(" ", strip=True)
            rate_text = tds[1].get_text(" ", strip=True)

            tenor_label, _days = self._normalize_tenor(tenor_text)
            rate = self._parse_vietnamese_float(self._clean_rate_text(rate_text))
            if not tenor_label or rate is None:
                continue

            record_date = applied_date or date.today()
            records.append(
                {
                    "date": record_date.strftime("%Y-%m-%d"),
                    "tenor_label": tenor_label,
                    "rate": rate,
                    "source": "SBV",
                    "fetched_at": datetime.now().isoformat(),
                }
            )

        return records

    def _clean_rate_text(self, text: str) -> str:
        """
        Clean SBV rate strings that may include footnotes like '(*)' or '(**)'.
        Example: '8,00 (*)' -> '8,00'
        """
        if not text:
            return ""

        cleaned = text.strip()
        cleaned = re.sub(r"\([^)]*\)", "", cleaned)  # remove parenthesized footnotes
        cleaned = cleaned.replace("*", "")
        cleaned = re.sub(r"[^0-9,.\-]+", "", cleaned)  # keep digits + separators + minus
        return cleaned.strip()

    def _normalize_tenor(self, text: str) -> tuple[str, int]:
        """Normalize Vietnamese tenor labels (e.g., 'Qua đêm', '1 Tuần', '3 Tháng')."""
        t = (text or "").strip().lower()

        # Direct map
        for vn, (label, days) in self.VIETNAMESE_TENORS.items():
            if vn in t:
                return label, days

        # Pattern-based map
        m = re.search(r"(\d+)\s*(tuần|tháng)", t)
        if m:
            value = int(m.group(1))
            unit = m.group(2)
            if unit == "tuần":
                return f"{value}W", value * 7
            if unit == "tháng":
                return f"{value}M", value * 30

        if "qua đêm" in t or "o/n" in t or "overnight" in t:
            return "ON", 0

        return "", 0

    def _fetch_playwright(self, target_date: date) -> List[Dict[str, Any]]:
        """Fetch using Playwright for JavaScript-rendered content"""
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright not available")
            return []

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=settings.playwright_headless)
                page = browser.new_page()

                # Navigate to URL
                page.goto(self.interbank_url, timeout=settings.playwright_timeout)

                # Wait for content to load
                page.wait_for_selector('table', timeout=10000)

                # Get HTML content
                html_content = page.content()

                # Save raw HTML
                self._save_raw(f"interbank_{target_date.strftime('%Y%m%d')}_playwright.html",
                              html_content.encode())

                browser.close()

                # Parse HTML
                soup = BeautifulSoup(html_content, 'html.parser')
                return self._parse_interbank_table(soup, target_date)

        except Exception as e:
            logger.error(f"Playwright fetch failed: {e}")
            return []

    def _parse_interbank_table(
        self,
        soup: BeautifulSoup,
        data_date: date
    ) -> List[Dict[str, Any]]:
        """
        Parse interbank rate table from HTML

        Args:
            soup: BeautifulSoup object
            data_date: Date of the data

        Returns:
            List of interbank rate records
        """
        records = []

        # Find tables
        tables = soup.find_all('table')
        logger.debug(f"Found {len(tables)} tables on page")

        for table_idx, table in enumerate(tables):
            try:
                rows = table.find_all('tr')
                if len(rows) < 2:
                    continue

                # Check if this looks like an interbank rate table
                sample_text = table.get_text()
                if not any(keyword in sample_text.lower() for keyword in
                          ['lãi suất', 'liên ngân hàng', 'interbank', 'on', 'tuần', 'tháng']):
                    continue

                # Parse data rows
                for row in rows[1:]:
                    cols = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]

                    if not cols or len(cols) < 2:
                        continue

                    # Identify tenor (first column)
                    tenor_text = cols[0] if cols else None

                    if not tenor_text:
                        continue

                    # Map tenor
                    tenor_info = self._match_tenor(tenor_text)
                    if not tenor_info:
                        continue

                    tenor_label, _ = tenor_info

                    # Extract rate (second column typically)
                    rate_value = None
                    if len(cols) > 1:
                        rate_value = self._parse_vietnamese_float(self._clean_rate_text(cols[1]))

                    if rate_value is not None:
                        record = {
                            'date': data_date.strftime('%Y-%m-%d'),
                            'tenor_label': tenor_label,
                            'rate': rate_value,
                            'source': 'SBV',
                            'fetched_at': datetime.now().isoformat()
                        }

                        records.append(record)

                if records:
                    logger.info(f"Parsed {len(records)} records from table {table_idx}")
                    break

            except Exception as e:
                logger.debug(f"Error parsing table {table_idx}: {e}")
                continue

        return records

    def _match_tenor(self, text: str) -> Optional[tuple[str, int]]:
        """
        Match Vietnamese/English tenor text to standardized tenor

        Args:
            text: Tenor text

        Returns:
            Tuple of (tenor_label, days) or None
        """
        text_normalized = text.strip().lower()

        # Try Vietnamese mappings first
        for vn_text, (label, days) in self.VIETNAMESE_TENORS.items():
            if vn_text in text_normalized or text_normalized in vn_text:
                return (label, days)

        # Try English mappings
        for en_text, (label, days) in self.TENOR_MAP.items():
            if en_text.lower() in text_normalized or text_normalized in en_text.lower():
                return (label, days)

        # Pattern matching
        match = re.search(r'(\d+)\s*(ngày|tháng|tuần|day|month|week)', text_normalized, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            unit = match.group(2).lower()

            if unit in ['ngày', 'day']:
                return (f'{value}D', value)
            elif unit in ['tuần', 'week']:
                return (f'{value}W', value * 7)
            elif unit in ['tháng', 'month']:
                return (f'{value}M', value * 30)

        return None
