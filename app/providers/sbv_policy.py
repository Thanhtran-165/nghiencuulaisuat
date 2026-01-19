"""
SBV Policy Rates Provider
Fetches State Bank of Vietnam policy rates

Historical Access Verdict: UNDER INVESTIGATION
- Using Playwright network discovery to find JSON/XHR endpoints
- Will determine if historical access is available
- Falls back to DOM scraping if no API found

Two-tier strategy:
- Tier 1: Look for official policy rates table
- Tier 2: Scrape decision pages for rate announcements
"""
import logging
import json
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import re

from app.providers.base import BaseProvider, ProviderError, ParseError, NotSupportedError
from app.config import settings

logger = logging.getLogger(__name__)


class SBVPolicyProvider(BaseProvider):
    """
    Provider for SBV Policy Rates

    Source: https://www.sbv.gov.vn

    Capability Flags:
    - supports_historical: TBD (after discovery)
    - supports_yesterday: TBD (after discovery)
    - supports_range_backfill: TBD (after discovery)

    Strategy: TBD (depends on endpoint discovery)
    """

    # Policy rate names (Vietnamese to English)
    RATE_NAMES = {
        'Lãi suất tái cấp vốn': 'Refinancing Rate',
        'Lãi suất tái chiết khấu': 'Rediscount Rate',
        'Lãi suất cơ bản': 'Base Rate',
        'Tỷ lệ dự trữ bắt buộc': 'Reserve Requirement Ratio',
        'Lãi suất OMO': 'OMO Rate',
        'Refinancing rate': 'Refinancing Rate',
        'Rediscount rate': 'Rediscount Rate',
        'Base rate': 'Base Rate',
    }

    def __init__(self):
        super().__init__()
        # SBV publishes policy rates on the public "Lãi suất" page.
        self.policy_url = f"{settings.sbv_base_url}/l%C3%A3i-su%E1%BA%A5t1"
        self.decision_url = f"{settings.sbv_base_url}"

        # Capability flags (determined after discovery)
        self.supports_historical = None  # TBD
        self.supports_yesterday = None  # TBD
        self.supports_range_backfill = None  # TBD

        # Discovered endpoints
        self.discovered_endpoints = {}

    def discover_endpoints(self) -> Dict[str, Any]:
        """
        Use Playwright to discover JSON/XHR endpoints for policy rates

        Returns:
            Dictionary with discovery results
        """
        logger.info("Running SBV Policy endpoint discovery...")

        discovery_result = {
            'provider': 'SBVPolicyProvider',
            'url': self.policy_url,
            'has_json_endpoint': False,
            'has_csv_endpoint': False,
            'has_date_picker': False,
            'has_api_endpoint': False,
            'json_endpoints_found': [],
            'api_endpoints_to_test': [],
            'recommendation': 'unknown',
            'raw_network_requests': []
        }

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=settings.playwright_headless)
                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                )
                page = context.new_page()

                # Track all network requests
                all_requests = []

                def handle_request(request):
                    url = request.url
                    resource_type = request.resource_type

                    request_info = {
                        'url': url,
                        'method': request.method,
                        'resource_type': resource_type,
                        'headers': dict(request.headers)
                    }

                    # Look for interesting endpoints
                    if any(pattern in url.lower() for pattern in ['.json', '/api/', '/ajax/', 'rate', 'lai-suat']):
                        discovery_result['json_endpoints_found'].append(request_info)

                    all_requests.append(request_info)

                page.on('request', handle_request)

                # Navigate to policy rates page
                logger.info(f"Navigating to {self.policy_url}")
                page.goto(self.policy_url, timeout=settings.playwright_timeout, wait_until='networkidle')

                # Wait for page to fully load
                page.wait_for_load_state('networkidle', timeout=10000)
                page.wait_for_timeout(2000)

                # Try to interact with filters or date pickers
                try:
                    # Look for any date inputs
                    date_inputs = page.query_selector_all('input[type="date"], input[type="text"][placeholder*="ngày"]')

                    if date_inputs:
                        logger.info(f"Found {len(date_inputs)} date input fields")

                    # Look for rate type selectors
                    selects = page.query_selector_all('select')
                    if selects:
                        logger.info(f"Found {len(selects)} select elements")

                except Exception as e:
                    logger.debug(f"Error interacting with form elements: {e}")

                # Check for data tables
                tables = page.query_selector_all('table')
                logger.info(f"Found {len(tables)} tables on page")

                # Look for policy rate indicators
                rate_elements = page.query_selector_all('*:has-text("Lãi suất"), *:has-text("tái cấp vốn")')
                logger.info(f"Found {len(rate_elements)} rate-related elements")

                # Store raw network data
                discovery_result['raw_network_requests'] = all_requests

                # Check for date picker elements
                date_pickers = page.query_selector_all('input[type="date"], input[type="text"][placeholder*="ngày"]')
                has_date_picker = len(date_pickers) > 0
                discovery_result['has_date_picker'] = has_date_picker

                browser.close()

                # Analyze discovered endpoints
                self._analyze_discovered_endpoints(discovery_result)

                # Store discovered endpoints for later use
                self.discovered_endpoints = discovery_result

                logger.info(f"Discovery complete: {discovery_result['recommendation']}")
                logger.info(f"  - Date picker: {has_date_picker}")
                logger.info(f"  - JSON endpoints: {len(discovery_result['json_endpoints_found'])}")
                logger.info(f"  - API endpoints to test: {len(discovery_result['api_endpoints_to_test'])}")

                # Update capability flags based on discovery
                if discovery_result['recommendation'] == 'historical_supported':
                    self.supports_historical = True
                    self.supports_yesterday = True
                    self.supports_range_backfill = True
                elif discovery_result['recommendation'] == 'latest_only':
                    self.supports_historical = False
                    self.supports_yesterday = False
                    self.supports_range_backfill = False
                else:
                    self.supports_historical = False
                    self.supports_yesterday = False
                    self.supports_range_backfill = False

                return discovery_result

        except Exception as e:
            logger.error(f"Error during endpoint discovery: {e}")
            discovery_result['discovery_error'] = str(e)
            discovery_result['recommendation'] = 'dom_scrape_fallback'
            return discovery_result

    def _analyze_discovered_endpoints(self, discovery_result: Dict[str, Any]):
        """
        Analyze discovered endpoints to determine capabilities

        Args:
            discovery_result: Discovery results dictionary to update
        """
        json_endpoints = discovery_result['json_endpoints_found']

        for endpoint in json_endpoints:
            url = endpoint['url'].lower()

            if any(keyword in url for keyword in ['date', 'from', 'start', 'ngay']):
                discovery_result['has_api_endpoint'] = True
                discovery_result['api_endpoints_to_test'].append(endpoint)
                discovery_result['recommendation'] = 'historical_possible'

            if 'policy' in url or 'rate' in url or 'lai-suat' in url:
                discovery_result['has_api_endpoint'] = True

        if discovery_result['api_endpoints_to_test']:
            discovery_result['recommendation'] = 'historical_supported'
        elif json_endpoints:
            discovery_result['recommendation'] = 'api_test_required'
        else:
            discovery_result['recommendation'] = 'dom_scrape_fallback'

    def fetch(self, target_date: date) -> List[Dict[str, Any]]:
        """
        Fetch policy rates for a specific date

        Args:
            target_date: Date to fetch data for

        Returns:
            List of policy rate records
        """
        logger.info(f"Fetching SBV policy rates for {target_date}")

        return self._fetch_from_dom(target_date)

    def _fetch_from_api(self, target_date: date, discovery: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Fetch policy rates from discovered API endpoints

        Args:
            target_date: Date to fetch
            discovery: Discovery results with endpoint info

        Returns:
            List of policy rate records
        """
        logger.info("Attempting to fetch from API endpoints...")

        for endpoint in discovery['api_endpoints_to_test']:
            try:
                url = endpoint['url']

                # Try to add date parameter
                separator = '&' if '?' in url else '?'
                test_url = f"{url}{separator}date={target_date.strftime('%Y-%m-%d')}"

                logger.debug(f"Testing endpoint: {test_url}")
                response = self._get(test_url)

                if response.status_code == 200:
                    try:
                        data = response.json()
                        records = self._parse_api_response(data, target_date)
                        if records:
                            return records
                    except:
                        logger.debug(f"Response not JSON or parse failed")

            except Exception as e:
                logger.debug(f"Endpoint {endpoint.get('url', 'unknown')} failed: {e}")
                continue

        return []

    def _parse_api_response(self, data: Any, target_date: date) -> List[Dict[str, Any]]:
        """
        Parse API response data

        Args:
            data: JSON response data
            target_date: Date of the data

        Returns:
            List of policy rate records
        """
        records = []

        try:
            if isinstance(data, dict):
                data_array = data.get('data') or data.get('results') or data.get('items') or []

                if isinstance(data_array, list):
                    for item in data_array:
                        record = self._parse_api_record(item, target_date)
                        if record:
                            records.append(record)

            elif isinstance(data, list):
                for item in data:
                    record = self._parse_api_record(item, target_date)
                    if record:
                        records.append(record)

        except Exception as e:
            logger.error(f"Error parsing API response: {e}")

        return records

    def _parse_api_record(self, item: Dict, target_date: date) -> Optional[Dict[str, Any]]:
        """
        Parse a single API record into standard format

        Args:
            item: Single record from API
            target_date: Date of the data

        Returns:
            Parsed policy rate record or None
        """
        try:
            record = {
                'date': target_date.strftime('%Y-%m-%d'),
                'rate_name': self._normalize_rate_name(item.get('rateName', item.get('name', ''))),
                'rate': self._parse_vietnamese_float(item.get('rate', item.get('value', ''))),
                'source': 'SBV_POLICY',
                'raw_file': json.dumps(item),
                'fetched_at': datetime.now().isoformat()
            }

            return record

        except Exception as e:
            logger.debug(f"Error parsing API record: {e}")
            return None

    def _fetch_from_dom(self, target_date: date) -> List[Dict[str, Any]]:
        """
        Fetch policy rates by scraping DOM

        Args:
            target_date: Date to fetch

        Returns:
            List of policy rate records
        """
        try:
            response = self._get(self.policy_url)
            self._save_raw(f"policy_rates_{target_date.strftime('%Y%m%d')}.html", response.content)

            soup = BeautifulSoup(response.content, 'html.parser')

            # Try Tier 1: Look for policy rates table
            records = self._parse_policy_table(soup, target_date)

            if not records:
                # Try Tier 2: Look for decision announcements
                logger.info("No policy rates table found, trying decision announcements")
                records = self._parse_decision_announcements(soup, target_date)

            if records:
                logger.info(f"Parsed {len(records)} records from DOM")
            else:
                logger.warning(f"No policy rate data found for {target_date}")

            return records

        except Exception as e:
            logger.error(f"Error fetching from DOM: {e}")
            raise ProviderError(f"Failed to fetch policy rates: {e}")

    def _parse_policy_table(self, soup: BeautifulSoup, data_date: date) -> List[Dict[str, Any]]:
        """
        Parse policy rates table from HTML

        Args:
            soup: BeautifulSoup object
            data_date: Date of the data

        Returns:
            List of policy rate records
        """
        records = []

        tables = soup.find_all('table')
        logger.debug(f"Found {len(tables)} tables on page")

        for table_idx, table in enumerate(tables):
            try:
                rows = table.find_all('tr')
                if len(rows) < 2:
                    continue

                headers = [th.get_text(strip=True) for th in rows[0].find_all(['th', 'td'])]

                header_text = ' '.join(headers).lower()

                # Policy table on SBV "Lãi suất" page: "Loại lãi suất | Giá trị | Văn bản quyết định | Ngày áp dụng"
                if 'loại lãi suất' not in header_text:
                    continue

                logger.debug(f"Table {table_idx}: headers = {headers}")

                for row in rows[1:]:
                    cols = [td.get_text(strip=True) for td in row.find_all('td')]

                    if not cols or len(cols) < 2:
                        continue

                    record = self._parse_policy_row(cols, data_date)
                    if record:
                        records.append(record)

                if records:
                    logger.info(f"Parsed {len(records)} records from table {table_idx}")
                    break

            except Exception as e:
                logger.debug(f"Error parsing table {table_idx}: {e}")
                continue

        return records

    def _parse_policy_row(self, cols: List[str], data_date: date) -> Optional[Dict[str, Any]]:
        """
        Parse a single policy rate table row

        Args:
            cols: List of column values
            data_date: Date of the data

        Returns:
            Policy rate record or None
        """
        try:
            rate_name = self._normalize_rate_name(cols[0]) if len(cols) > 0 else ''
            rate_value = self._parse_vietnamese_float(cols[1]) if len(cols) > 1 else None
            applied_date = None
            if len(cols) > 3:
                applied_date = self._standardize_date(cols[3], ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'])

            if not rate_name or rate_value is None:
                return None

            record = {
                'date': (applied_date or data_date).strftime('%Y-%m-%d'),
                'rate_name': rate_name,
                'rate': rate_value,
                'source': 'SBV_POLICY',
                'raw_file': cols[2] if len(cols) > 2 else '|'.join(cols),
                'fetched_at': datetime.now().isoformat()
            }

            return record

        except Exception as e:
            logger.debug(f"Error parsing policy row: {e}")
            return None

    def _parse_decision_announcements(self, soup: BeautifulSoup, data_date: date) -> List[Dict[str, Any]]:
        """
        Parse decision announcements for policy rates

        Args:
            soup: BeautifulSoup object
            data_date: Date of the data

        Returns:
            List of policy rate records
        """
        records = []

        # Look for decision/announcement sections
        announcements = soup.find_all(['div', 'section', 'article'],
                                      class_=re.compile(r'(decision|quyet-dinh|announcement|thong-bao)', re.I))

        for ann in announcements[:5]:  # Limit to first 5 announcements
            try:
                text = ann.get_text(strip=True)

                # Look for rate mentions in the text
                rate_pattern = r'(\d+[,.]?\d*)\s*%'

                for match in re.finditer(rate_pattern, text):
                    rate_value = match.group(1).replace(',', '.')

                    # Try to determine rate type from context
                    rate_name = 'Unknown Rate'
                    if 'tái cấp' in text.lower() or 'refinancing' in text.lower():
                        rate_name = 'Refinancing Rate'
                    elif 'chiết khấu' in text.lower() or 'rediscount' in text.lower():
                        rate_name = 'Rediscount Rate'
                    elif 'cơ bản' in text.lower() or 'base' in text.lower():
                        rate_name = 'Base Rate'

                    record = {
                        'date': data_date.strftime('%Y-%m-%d'),
                        'rate_name': rate_name,
                        'rate': float(rate_value),
                        'source': 'SBV_POLICY',
                        'raw_file': text[:500],  # Store first 500 chars
                        'fetched_at': datetime.now().isoformat()
                    }

                    records.append(record)

            except Exception as e:
                logger.debug(f"Error parsing announcement: {e}")
                continue

        return records

    def backfill(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        Backfill policy rates for a date range

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            List of all policy rate records in range

        Raises:
            NotSupportedError: If historical access not available
        """
        if self.supports_historical is None:
            self.discover_endpoints()

        if not self.supports_historical:
            raise NotSupportedError(
                "SBV policy rates do not support historical backfill. "
                "The public interface only provides current rates. "
                "Use daily snapshot accumulation: run 'python -m app.ingest daily' "
                "to accumulate data from your start date."
            )

        logger.info(f"Backfilling policy rates from {start_date} to {end_date}")

        all_records = []
        current_date = start_date

        while current_date <= end_date:
            logger.info(f"Fetching policy rates for {current_date}")
            try:
                records = self.fetch(current_date)
                all_records.extend(records)
            except Exception as e:
                logger.error(f"Failed to fetch {current_date}: {e}")

            current_date += timedelta(days=1)

        logger.info(f"Backfill complete: {len(all_records)} total records")
        return all_records

    def _normalize_rate_name(self, text: str) -> str:
        """
        Normalize Vietnamese rate name to standard English

        Args:
            text: Vietnamese text

        Returns:
            Normalized rate name
        """
        text_normalized = text.strip().lower()

        for vn_text, en_text in self.RATE_NAMES.items():
            if vn_text.lower() in text_normalized:
                return en_text

        return text

    def _parse_vietnamese_float(self, text: str) -> Optional[float]:
        """
        Parse Vietnamese float with comma as decimal separator

        Args:
            text: Vietnamese float text

        Returns:
            Parsed float or None
        """
        if not text:
            return None

        try:
            # Handle Vietnamese number format
            cleaned = text.replace('%', '').replace(',', '.').strip()
            return float(cleaned) if cleaned else None
        except:
            return None
