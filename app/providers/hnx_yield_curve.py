"""
HNX Yield Curve Provider
Fetches government bond yield curve data from HNX website

Historical Access Verdict: HISTORICAL SUPPORTED (by date)
- HNX exposes a server-rendered POST endpoint that returns the yield curve table for a given date (`pDate=dd/mm/YYYY`).
- Historical backfill is supported by iterating dates and persisting daily snapshots.
"""
import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import re
import time

from app.providers.base import BaseProvider, ProviderError, ParseError, NotSupportedError
from app.config import settings

logger = logging.getLogger(__name__)


class HNXYieldCurveProvider(BaseProvider):
    """
    Provider for HNX Government Bond Yield Curve data

    Source: https://hnx.vn/trai-phieu/duong-cong-loi-suat.html

    Capability Flags:
    - supports_historical: True (date-based endpoint)
    - supports_yesterday: True
    - supports_range_backfill: True

    Strategy: Request-by-date snapshots and persist to build history
    """

    # Tenor mappings (Vietnamese to English)
    TENOR_MAP = {
        '3 tháng': ('3M', 90),
        '6 tháng': ('6M', 180),
        '9 tháng': ('9M', 270),
        '1 năm': ('1Y', 365),
        '2 năm': ('2Y', 730),
        '3 năm': ('3Y', 1095),
        '5 năm': ('5Y', 1825),
        '7 năm': ('7Y', 2555),
        '10 năm': ('10Y', 3650),
        '15 năm': ('15Y', 5475),
        '20 năm': ('20Y', 7300),
    }

    DATE_FORMATS = [
        '%d/%m/%Y',
        '%Y-%m-%d',
        '%d-%m-%Y',
    ]

    def __init__(self):
        super().__init__()
        self.yield_curve_url = f"{settings.hnx_base_url}/trai-phieu/duong-cong-loi-suat.html"
        self.yield_curve_search_url = (
            f"{settings.hnx_base_url}/ModuleReportBonds/Bond_YieldCurve/SearchAndNextPageYieldCurveData"
        )

        # Capability flags (confirmed via date-based endpoint)
        self.supports_historical = True
        self.supports_yesterday = True
        self.supports_range_backfill = True

    def fetch(self, target_date: date) -> List[Dict[str, Any]]:
        """
        Fetch yield curve data for a specific date

        Args:
            target_date: Date to fetch

        Returns:
            List of yield curve records for the requested date (or empty if unavailable)
        """
        logger.info(f"Fetching HNX yield curve for {target_date}")

        try:
            # HNX renders the yield curve table via an internal POST endpoint.
            # Use it to retrieve server-rendered HTML for a given date.
            response = self._post(
                self.yield_curve_search_url,
                data={"pDate": target_date.strftime("%d/%m/%Y")},
            )
            self._save_raw(
                f"yield_curve_partial_{target_date.strftime('%Y%m%d')}.html",
                response.content,
            )

            if "Không tìm thấy dữ liệu" in response.text:
                logger.info(f"No yield curve data available for {target_date}")
                return []

            soup = BeautifulSoup(response.content, "html.parser")
            records = self._parse_yield_curve_partial(soup, target_date)

            if not records:
                # Fallback: attempt to parse the main page in case the endpoint changes.
                logger.info("Yield curve partial returned no rows; falling back to main page scrape")
                page = self._get(self.yield_curve_url)
                self._save_raw(f"yield_curve_{target_date.strftime('%Y%m%d')}.html", page.content)
                soup2 = BeautifulSoup(page.content, "html.parser")
                records = self._parse_yield_curve_table(soup2, target_date)

                if not records:
                    logger.warning(f"No yield curve data found for {target_date}")
                    return []

            logger.info(f"Found {len(records)} yield curve records for {target_date}")
            return records

        except Exception as e:
            logger.error(f"Error fetching yield curve for {target_date}: {e}")
            raise ProviderError(f"Failed to fetch yield curve: {e}")

    def backfill(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        Backfill yield curve data for a date range

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        """
        logger.info(f"Backfilling HNX yield curve from {start_date} to {end_date}")

        all_records: list[dict] = []
        current_date = start_date
        while current_date <= end_date:
            try:
                all_records.extend(self.fetch(current_date))
            except Exception as e:
                logger.warning(f"Failed to fetch yield curve for {current_date}: {e}")

            # Respect a light rate limit to be polite to HNX.
            if settings.rate_limit_seconds and settings.rate_limit_seconds > 0:
                time.sleep(float(settings.rate_limit_seconds))

            current_date += timedelta(days=1)

        logger.info(f"Backfill complete: {len(all_records)} total yield curve records")
        return all_records

    def discover_endpoints(self) -> Dict[str, Any]:
        """
        Use Playwright to discover if there are any hidden JSON/CSV endpoints
        that support historical data access.

        Returns:
            Dictionary with discovery results
        """
        logger.info("Running HNX endpoint discovery...")

        discovery_result = {
            'provider': 'HNXYieldCurveProvider',
            'url': self.yield_curve_url,
            'has_json_endpoint': False,
            'has_csv_endpoint': False,
            'has_date_picker': False,
            'has_api_endpoint': False,
            'json_endpoints_found': [],
            'recommendation': 'latest_only'
        }

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=settings.playwright_headless)
                page = browser.new_page()

                # Track network requests
                json_endpoints = []
                csv_endpoints = []

                def handle_request(request):
                    url = request.url
                    # Look for API endpoints
                    if '.json' in url.lower() or '/api/' in url.lower():
                        json_endpoints.append({
                            'url': url,
                            'method': request.method,
                            'resource_type': request.resource_type
                        })
                    if '.csv' in url.lower():
                        csv_endpoints.append(url)

                page.on('request', handle_request)

                # Navigate to yield curve page
                logger.info(f"Navigating to {self.yield_curve_url}")
                page.goto(self.yield_curve_url, timeout=settings.playwright_timeout)

                # Wait for page to load
                page.wait_for_load_state('networkidle', timeout=10000)

                # Check for date picker elements
                date_pickers = page.query_selector_all('input[type="date"], input[type="text"][placeholder*="date"], select[name*="date"]')
                has_date_picker = len(date_pickers) > 0

                # Look for API calls in network log
                # (Already captured by request handler)

                browser.close()

                # Update discovery results
                discovery_result['has_json_endpoint'] = len(json_endpoints) > 0
                discovery_result['has_csv_endpoint'] = len(csv_endpoints) > 0
                discovery_result['has_date_picker'] = has_date_picker
                discovery_result['json_endpoints_found'] = json_endpoints

                # Determine recommendation
                if json_endpoints:
                    # Check if any endpoint has date parameter
                    for endpoint in json_endpoints:
                        if 'date' in endpoint['url'].lower() or 'from' in endpoint['url'].lower():
                            discovery_result['recommendation'] = 'historical_possible'
                            discovery_result['has_api_endpoint'] = True
                            break
                else:
                    discovery_result['recommendation'] = 'latest_only'

                logger.info(f"Discovery complete: {discovery_result['recommendation']}")
                logger.info(f"  - Date picker: {has_date_picker}")
                logger.info(f"  - JSON endpoints: {len(json_endpoints)}")
                logger.info(f"  - CSV endpoints: {len(csv_endpoints)}")

                return discovery_result

        except Exception as e:
            logger.error(f"Error during endpoint discovery: {e}")
            discovery_result['discovery_error'] = str(e)
            return discovery_result

    def _parse_yield_curve_table(self, soup: BeautifulSoup, data_date: date) -> List[Dict[str, Any]]:
        """
        Parse yield curve table from HTML

        Args:
            soup: BeautifulSoup object
            data_date: Date of the data

        Returns:
            List of yield curve records
        """
        records = []

        # Try multiple table selection strategies
        tables = soup.find_all('table')
        logger.debug(f"Found {len(tables)} tables on page")

        for table_idx, table in enumerate(tables):
            try:
                rows = table.find_all('tr')
                if len(rows) < 2:
                    continue

                # Check if this looks like a yield curve table
                headers = [th.get_text(strip=True) for th in rows[0].find_all(['th', 'td'])]

                # Look for tenor-related headers
                if not any(keyword in ' '.join(headers).lower() for keyword in
                          ['kỳ hạn', 'tháng', 'năm', 'tenor', 'lợi suất']):
                    continue

                logger.debug(f"Table {table_idx}: headers = {headers}")

                # Parse data rows
                for row in rows[1:]:
                    cols = [td.get_text(strip=True) for td in row.find_all('td')]

                    if not cols or len(cols) < 2:
                        continue

                    # Try to identify tenor column
                    tenor_text = cols[0] if cols else None

                    if not tenor_text:
                        continue

                    # Map tenor
                    tenor_info = self._match_tenor(tenor_text)
                    if not tenor_info:
                        continue

                    tenor_label, tenor_days = tenor_info

                    # Try to extract yield (second column typically)
                    yield_value = None
                    if len(cols) > 1:
                        yield_value = self._parse_vietnamese_float(cols[1])

                    record = {
                        'date': data_date.strftime('%Y-%m-%d'),
                        'tenor_label': tenor_label,
                        'tenor_days': tenor_days,
                        'spot_rate_continuous': yield_value,
                        'par_yield': yield_value,  # Assume same if not specified
                        'spot_rate_annual': yield_value,  # Assume same if not specified
                        'source': 'HNX_YC',
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

    def _parse_yield_curve_partial(self, soup: BeautifulSoup, data_date: date) -> List[Dict[str, Any]]:
        """
        Parse yield curve HTML returned by SearchAndNextPageYieldCurveData.

        Expected columns:
          - Kỳ hạn còn lại (tenor)
          - Spot rate liên tục (%)
          - Par yield (%)
          - Spot rate theo năm (%)
        """
        table = soup.find("table", id="_tableDatas")
        if table is None:
            return []

        rows = table.find_all("tr")
        if len(rows) < 2:
            return []

        records: list[dict] = []
        for row in rows[1:]:
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) < 2:
                continue

            tenor_text = cols[0]
            tenor_info = self._match_tenor(tenor_text)
            if not tenor_info:
                continue

            tenor_label, tenor_days = tenor_info
            spot_cont = self._parse_vietnamese_float(cols[1]) if len(cols) > 1 else None
            par_yield = self._parse_vietnamese_float(cols[2]) if len(cols) > 2 else None
            spot_annual = self._parse_vietnamese_float(cols[3]) if len(cols) > 3 else None

            records.append(
                {
                    "date": data_date.strftime("%Y-%m-%d"),
                    "tenor_label": tenor_label,
                    "tenor_days": tenor_days,
                    "spot_rate_continuous": spot_cont,
                    "par_yield": par_yield,
                    "spot_rate_annual": spot_annual,
                    "source": "HNX_YC",
                    "fetched_at": datetime.now().isoformat(),
                }
            )

        return records

    def _match_tenor(self, text: str) -> Optional[tuple[str, int]]:
        """
        Match Vietnamese tenor text to standardized tenor

        Args:
            text: Vietnamese tenor text

        Returns:
            Tuple of (tenor_label, tenor_days) or None
        """
        text_normalized = text.strip().lower()

        # Direct match
        for vn_text, (label, days) in self.TENOR_MAP.items():
            if vn_text.lower() in text_normalized or text_normalized in vn_text.lower():
                return (label, days)

        # Pattern matching for numbers
        # Compact forms like "2Y", "5Y", "3M"
        match = re.fullmatch(r'(\d+)\s*([MY])', text_normalized.upper())
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            if unit == 'M':
                return (f'{value}M', value * 30)
            if unit == 'Y':
                return (f'{value}Y', value * 365)

        match = re.search(r'(\d+)\s*(tháng|năm|month|year)', text_normalized, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            unit = match.group(2).lower()

            if unit in ['tháng', 'month']:
                return (f'{value}M', value * 30)
            elif unit in ['năm', 'year']:
                return (f'{value}Y', value * 365)

        return None
