"""
HNX Auction Provider
Fetches government bond auction results from HNX website

Historical Access Verdict: UNDER INVESTIGATION
- Using Playwright network discovery to find JSON/XHR endpoints
- Will determine if historical access is available
- Falls back to DOM scraping if no API found
"""
import logging
import json
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import re
import time

from app.providers.base import BaseProvider, ProviderError, ParseError, NotSupportedError
from app.config import settings

logger = logging.getLogger(__name__)


class HNXAuctionProvider(BaseProvider):
    """
    Provider for HNX Government Bond Auction Results

    Source: https://hnx.vn/trai-phieu/dau-gia-trai-phieu.html

    Capability Flags:
    - supports_historical: TBD (after discovery)
    - supports_yesterday: TBD (after discovery)
    - supports_range_backfill: TBD (after discovery)

    Strategy: TBD (depends on endpoint discovery)
    """

    # Instrument type mappings (Vietnamese to English)
    INSTRUMENT_MAP = {
        'Trái phiếu chính phủ': 'Government Bond',
        'Tín phiếu kho bạc': 'T-Bill',
        'TP Kho bạc': 'T-Bill',
        'Trái phiếu': 'Government Bond',
    }

    # Tenor mappings
    TENOR_MAP = {
        '3 tháng': ('3M', 90),
        '6 tháng': ('6M', 180),
        '9 tháng': ('9M', 270),
        '12 tháng': ('12M', 365),
        '1 năm': ('1Y', 365),
        '2 năm': ('2Y', 730),
        '3 năm': ('3Y', 1095),
        '5 năm': ('5Y', 1825),
        '7 năm': ('7Y', 2555),
        '10 năm': ('10Y', 3650),
        '15 năm': ('15Y', 5475),
        '20 năm': ('20Y', 7300),
    }

    def __init__(self):
        super().__init__()
        self.auction_url = f"{settings.hnx_base_url}/trai-phieu/dau-gia-trai-phieu.html"
        self.auction_results_url = (
            f"{settings.hnx_base_url}/ModuleReportBonds/Bond_DauThau/Bond_KetQua_DauThau"
        )
        self.auction_results_default_url = (
            f"{settings.hnx_base_url}/ModuleReportBonds/Bond_DauThau/Bond_KetQua_DauThau_Default"
        )

        # Capability flags (confirmed via internal POST endpoint)
        self.supports_historical = True
        self.supports_yesterday = True
        self.supports_range_backfill = True

        # Discovered endpoints
        self.discovered_endpoints = {}

    def discover_endpoints(self) -> Dict[str, Any]:
        """
        Use Playwright to discover JSON/XHR endpoints for auction data

        Returns:
            Dictionary with discovery results
        """
        logger.info("Running HNX Auction endpoint discovery...")

        discovery_result = {
            'provider': 'HNXAuctionProvider',
            'url': self.auction_url,
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

                    # Capture request details
                    request_info = {
                        'url': url,
                        'method': request.method,
                        'resource_type': resource_type,
                        'headers': dict(request.headers)
                    }

                    # Look for interesting endpoints
                    if any(pattern in url.lower() for pattern in ['.json', '/api/', '/ajax/', 'auction', 'dau-gia']):
                        discovery_result['json_endpoints_found'].append(request_info)

                    all_requests.append(request_info)

                def handle_response(response):
                    # Log response status for interesting requests
                    if any(pattern in response.url.lower() for pattern in ['.json', '/api/', '/ajax/']):
                        logger.debug(f"API Response: {response.url} - Status: {response.status}")

                page.on('request', handle_request)
                page.on('response', handle_response)

                # Navigate to auction page
                logger.info(f"Navigating to {self.auction_url}")
                page.goto(self.auction_url, timeout=settings.playwright_timeout, wait_until='networkidle')

                # Wait for page to fully load
                page.wait_for_load_state('networkidle', timeout=10000)
                page.wait_for_timeout(2000)  # Extra wait for dynamic content

                # Try to interact with date pickers or filters
                try:
                    # Look for date input fields
                    date_inputs = page.query_selector_all('input[type="date"], input[type="text"][placeholder*="ngày"], input[placeholder*="date"]')

                    if date_inputs:
                        logger.info(f"Found {len(date_inputs)} date input fields")

                        # Try interacting with first date picker
                        for date_input in date_inputs[:1]:  # Only test first one
                            try:
                                date_input.click()
                                page.wait_for_timeout(500)
                            except:
                                pass

                    # Look for filter buttons or search buttons
                    search_buttons = page.query_selector_all('button[type="submit"], button:has-text("Tìm"), button:has-text("Lọc"), button:has-text("Search")')

                    if search_buttons:
                        logger.info(f"Found {len(search_buttons)} search/filter buttons")
                        # Click first search button to trigger API calls
                        try:
                            search_buttons[0].click()
                            page.wait_for_timeout(2000)
                        except:
                            pass

                except Exception as e:
                    logger.debug(f"Error interacting with form elements: {e}")

                # Check for data tables
                tables = page.query_selector_all('table')
                logger.info(f"Found {len(tables)} tables on page")

                # Look for pagination or load more buttons
                pagination = page.query_selector_all('button:has-text("Load"), a:has-text("Tiếp"), a:has-text("Next")')
                if pagination:
                    logger.info(f"Found {len(pagination)} pagination/load more elements")

                    # Try clicking to load more data and capture API calls
                    try:
                        pagination[0].click()
                        page.wait_for_timeout(2000)
                    except:
                        pass

                # Store raw network data
                discovery_result['raw_network_requests'] = all_requests

                # Check for date picker elements
                date_pickers = page.query_selector_all('input[type="date"], input[type="text"][placeholder*="ngày"], select[name*="date"]')
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
                else:  # fallback to DOM scraping
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

        # Look for promising endpoints
        for endpoint in json_endpoints:
            url = endpoint['url'].lower()

            # Check for date parameters
            if any(keyword in url for keyword in ['date', 'from', 'start', 'ngay']):
                discovery_result['has_api_endpoint'] = True
                discovery_result['api_endpoints_to_test'].append(endpoint)
                discovery_result['recommendation'] = 'historical_possible'

            # Check for auction-specific endpoints
            if 'auction' in url or 'dau-gia' in url:
                discovery_result['has_api_endpoint'] = True

        # Determine final recommendation
        if discovery_result['api_endpoints_to_test']:
            # Found endpoints with date parameters
            discovery_result['recommendation'] = 'historical_supported'
        elif json_endpoints:
            # Found JSON endpoints but no clear date parameter
            discovery_result['recommendation'] = 'api_test_required'
        else:
            # No JSON endpoints found
            discovery_result['recommendation'] = 'dom_scrape_fallback'

    def fetch(self, target_date: date) -> List[Dict[str, Any]]:
        """
        Fetch auction results for a specific date

        Args:
            target_date: Date to fetch data for

        Returns:
            List of auction result records
        """
        logger.info(f"Fetching HNX auction results for {target_date}")

        try:
            html, raw_file = self._fetch_results_html(target_date, target_date, page=1, per_page=200)
            soup = BeautifulSoup(html, "html.parser")
            records = self._parse_auction_results_table(soup, raw_file=raw_file, expected_date=target_date)

            if records:
                logger.info(f"Found {len(records)} auction results for {target_date}")
                return records

            # Fallback: if HNX returns no results for the requested date, fetch the default view
            # and return the latest date present (best-effort "latest available").
            logger.info("No auction results for requested date; falling back to latest available")
            resp = self._post(self.auction_results_default_url, data={"pColOrder": "", "pOrderType": ""})
            raw_path = self._save_raw(
                f"hnx_auction_default_{target_date.strftime('%Y%m%d')}.html",
                resp.content,
            )
            raw_file = str(raw_path) if raw_path else None
            soup2 = BeautifulSoup(resp.content, "html.parser")
            all_records = self._parse_auction_results_table(soup2, raw_file=raw_file, expected_date=None)
            if not all_records:
                return []

            # Keep only latest date in the default snapshot.
            latest = max(r["date"] for r in all_records if r.get("date"))
            return [r for r in all_records if r.get("date") == latest]

        except Exception as e:
            logger.error(f"Error fetching HNX auction results for {target_date}: {e}")
            raise ProviderError(f"Failed to fetch HNX auction results: {e}")

    def _fetch_from_api(self, target_date: date, discovery: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Fetch auction data from discovered API endpoints

        Args:
            target_date: Date to fetch
            discovery: Discovery results with endpoint info

        Returns:
            List of auction records
        """
        logger.info("Attempting to fetch from API endpoints...")

        # Try each discovered endpoint
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
            List of auction records
        """
        records = []

        try:
            # Handle different response formats
            if isinstance(data, dict):
                # Look for data array in common keys
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
            Parsed auction record or None
        """
        try:
            # Map API fields to database schema
            # This will need to be adjusted based on actual API response
            record = {
                'date': target_date.strftime('%Y-%m-%d'),
                'instrument_type': self._normalize_instrument_type(item.get('instrumentType', item.get('type', ''))),
                'tenor_label': item.get('tenor', item.get('tenorLabel', '')),
                'tenor_days': self._parse_tenor_days(item.get('tenor', item.get('tenorLabel', ''))),
                'amount_offered': self._parse_vietnamese_number(item.get('amountOffered', item.get('offeredAmount', ''))),
                'amount_sold': self._parse_vietnamese_number(item.get('amountSold', item.get('soldAmount', ''))),
                'bid_to_cover': self._parse_vietnamese_float(item.get('bidToCover', item.get('bidCover', ''))),
                'cut_off_yield': self._parse_vietnamese_float(item.get('cutOffYield', item.get('cutoffYield', ''))),
                'avg_yield': self._parse_vietnamese_float(item.get('avgYield', item.get('averageYield', ''))),
                'source': 'HNX_AUCTION',
                'raw_file': json.dumps(item),
                'fetched_at': datetime.now().isoformat()
            }

            return record

        except Exception as e:
            logger.debug(f"Error parsing API record: {e}")
            return None

    def _fetch_from_dom(self, target_date: date) -> List[Dict[str, Any]]:
        """
        Fetch auction data by scraping DOM

        Args:
            target_date: Date to fetch

        Returns:
            List of auction records
        """
        try:
            response = self._get(self.auction_url)
            self._save_raw(f"auction_{target_date.strftime('%Y%m%d')}.html", response.content)

            soup = BeautifulSoup(response.content, 'html.parser')
            records = self._parse_auction_table(soup, target_date)

            if records:
                logger.info(f"Parsed {len(records)} records from DOM")
            else:
                logger.warning(f"No auction data found for {target_date}")

            return records

        except Exception as e:
            logger.error(f"Error fetching from DOM: {e}")
            raise ProviderError(f"Failed to fetch auction data: {e}")

    def _parse_auction_table(self, soup: BeautifulSoup, data_date: date) -> List[Dict[str, Any]]:
        """
        Parse auction table from HTML

        Args:
            soup: BeautifulSoup object
            data_date: Date of the data

        Returns:
            List of auction records
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

                # Check if this looks like an auction table
                headers = [th.get_text(strip=True) for th in rows[0].find_all(['th', 'td'])]

                # Look for auction-related keywords
                if not any(keyword in ' '.join(headers).lower() for keyword in
                          ['đấu thầu', 'auction', 'khố lượng', 'volume', 'lợi suất', 'yield']):
                    continue

                logger.debug(f"Table {table_idx}: headers = {headers}")

                # Parse data rows
                for row in rows[1:]:
                    cols = [td.get_text(strip=True) for td in row.find_all('td')]

                    if not cols or len(cols) < 3:
                        continue

                    record = self._parse_auction_row(cols, data_date)
                    if record:
                        records.append(record)

                if records:
                    logger.info(f"Parsed {len(records)} records from table {table_idx}")
                    break

            except Exception as e:
                logger.debug(f"Error parsing table {table_idx}: {e}")
                continue

        return records

    def _parse_auction_row(self, cols: List[str], data_date: date) -> Optional[Dict[str, Any]]:
        """
        Parse a single auction table row

        Args:
            cols: List of column values
            data_date: Date of the data

        Returns:
            Auction record or None
        """
        try:
            # Extract values based on column position
            # This will need to be adjusted based on actual table structure
            instrument_type = self._normalize_instrument_type(cols[0]) if len(cols) > 0 else ''
            tenor_text = cols[1] if len(cols) > 1 else ''
            amount_offered = self._parse_vietnamese_number(cols[2]) if len(cols) > 2 else None
            amount_sold = self._parse_vietnamese_number(cols[3]) if len(cols) > 3 else None
            bid_to_cover = self._parse_vietnamese_float(cols[4]) if len(cols) > 4 else None
            cut_off_yield = self._parse_vietnamese_float(cols[5]) if len(cols) > 5 else None
            avg_yield = self._parse_vietnamese_float(cols[6]) if len(cols) > 6 else None

            tenor_label, tenor_days = self._match_tenor(tenor_text)

            if not instrument_type or not tenor_label:
                return None

            record = {
                'date': data_date.strftime('%Y-%m-%d'),
                'instrument_type': instrument_type,
                'tenor_label': tenor_label,
                'tenor_days': tenor_days,
                'amount_offered': amount_offered,
                'amount_sold': amount_sold,
                'bid_to_cover': bid_to_cover,
                'cut_off_yield': cut_off_yield,
                'avg_yield': avg_yield,
                'source': 'HNX_AUCTION',
                'raw_file': '|'.join(cols),
                'fetched_at': datetime.now().isoformat()
            }

            return record

        except Exception as e:
            logger.debug(f"Error parsing auction row: {e}")
            return None

    def backfill(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        Backfill auction results for a date range

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            List of all auction records in range

        Raises:
            NotSupportedError: If historical access not available
        """
        logger.info(f"Backfilling auction results from {start_date} to {end_date}")

        # Use HNX range-search endpoint instead of day-by-day scanning.
        try:
            records = self._fetch_range(start_date, end_date)
            logger.info(f"Backfill complete: {len(records)} total records")
            return records
        except Exception as e:
            logger.warning(f"Range backfill failed ({e}); falling back to day-by-day")

        all_records: list[dict] = []
        current_date = start_date
        while current_date <= end_date:
            try:
                all_records.extend(self.fetch(current_date))
            except Exception as e:
                logger.error(f"Failed to fetch {current_date}: {e}")

            if settings.rate_limit_seconds and settings.rate_limit_seconds > 0:
                time.sleep(float(settings.rate_limit_seconds))
            current_date += timedelta(days=1)

        logger.info(f"Backfill complete: {len(all_records)} total records")
        return all_records

    def _build_keysearch(self, from_date: date, to_date: date) -> str:
        """
        Build HNX Bond_DauThau search key.

        Format (8 fields, pipe-separated):
          from|to|typeAMT|bond_period|period_unit|accycde|tcph|stock_type
        """
        # Use broadly-inclusive defaults for non-date filters.
        # accycde expects quotes in the upstream JS ("'VND'").
        return (
            f"{from_date.strftime('%d/%m/%Y')}|{to_date.strftime('%d/%m/%Y')}||0|3|'VND'|0|0"
        )

    def _fetch_results_html(
        self,
        from_date: date,
        to_date: date,
        page: int,
        per_page: int,
    ) -> tuple[bytes, Optional[str]]:
        keysearch = self._build_keysearch(from_date, to_date)
        resp = self._post(
            self.auction_results_url,
            data={
                "p_keysearch": keysearch,
                "pColOrder": "",
                "pOrderType": "",
                "pCurrentPage": int(page),
                "pRecordOnPage": int(per_page),
                "pIsSearch": 1,
            },
        )
        raw_path = self._save_raw(
            f"hnx_auction_{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}_p{page}.html",
            resp.content,
        )
        return resp.content, str(raw_path) if raw_path else None

    def _parse_total_records(self, html_text: str) -> Optional[int]:
        m = re.search(r"Tổng số\\s+(\\d+)\\s+bản ghi", html_text)
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:
            return None

    def _fetch_range(self, from_date: date, to_date: date) -> List[Dict[str, Any]]:
        """
        Fetch all auction results within a date range using paging.
        """
        per_page = 200
        total_pages: Optional[int] = None
        all_records: list[dict] = []
        raw_file: Optional[str] = None

        for page in range(1, 200):  # safety cap
            html, page_raw_file = self._fetch_results_html(from_date, to_date, page=page, per_page=per_page)
            if raw_file is None:
                raw_file = page_raw_file

            soup = BeautifulSoup(html, "html.parser")
            all_records.extend(self._parse_auction_results_table(soup, raw_file=raw_file, expected_date=None))

            if total_pages is None:
                total = self._parse_total_records(html.decode("utf-8", errors="ignore"))
                if total is not None:
                    total_pages = max(1, (total + per_page - 1) // per_page)

            if total_pages is not None and page >= total_pages:
                break

            if total_pages is None:
                # No paging metadata; stop when a page yields no rows.
                if not soup.find("table", id="_tableDatas") or not soup.select("table#_tableDatas tbody tr"):
                    break

            if settings.rate_limit_seconds and settings.rate_limit_seconds > 0:
                time.sleep(float(settings.rate_limit_seconds))

        return all_records

    def _parse_auction_results_table(
        self,
        soup: BeautifulSoup,
        raw_file: Optional[str],
        expected_date: Optional[date],
    ) -> List[Dict[str, Any]]:
        table = soup.find("table", id="_tableDatas")
        if not table:
            return []

        header_cells = table.select("thead th")
        headers = [h.get_text(" ", strip=True).casefold() for h in header_cells]

        def find_idx(*needles: str) -> Optional[int]:
            for i, h in enumerate(headers):
                if any(n in h for n in needles):
                    return i
            return None

        idx_tenor = find_idx("kỳ hạn")
        idx_ngay_tcph = find_idx("ngày tcph", "ngày tổ chức")
        idx_gt_goi_thau = find_idx("gt gọi thầu")
        idx_gt_dat_thau = find_idx("gt đặt thầu")
        idx_gt_trung_thau = find_idx("gt trúng thầu")
        idx_ls_trung_thau = find_idx("lãi suất trúng thầu")
        idx_ls_danh_nghia = find_idx("lãi suất danh nghĩa")

        if idx_tenor is None or idx_ngay_tcph is None:
            return []

        now = datetime.now().isoformat()
        records: list[dict] = []

        for tr in table.select("tbody tr"):
            tds = tr.find_all("td")
            cols = [td.get_text(" ", strip=True) for td in tds]

            if idx_ngay_tcph >= len(cols) or idx_tenor >= len(cols):
                continue

            row_date_str = cols[idx_ngay_tcph]
            try:
                row_date = datetime.strptime(row_date_str, "%d/%m/%Y").date()
            except Exception:
                continue

            if expected_date is not None and row_date != expected_date:
                continue

            tenor_text = cols[idx_tenor]
            tenor_label, tenor_days = self._match_tenor(tenor_text)
            if tenor_label == "Unknown" or tenor_days <= 0:
                continue

            instrument_type = "T-Bill" if tenor_days <= 365 else "Government Bond"

            amount_offered = (
                self._parse_vietnamese_float(cols[idx_gt_goi_thau])
                if idx_gt_goi_thau is not None and idx_gt_goi_thau < len(cols)
                else None
            )
            total_bids = (
                self._parse_vietnamese_float(cols[idx_gt_dat_thau])
                if idx_gt_dat_thau is not None and idx_gt_dat_thau < len(cols)
                else None
            )
            amount_sold = (
                self._parse_vietnamese_float(cols[idx_gt_trung_thau])
                if idx_gt_trung_thau is not None and idx_gt_trung_thau < len(cols)
                else None
            )

            bid_to_cover = None
            if amount_offered and amount_offered > 0 and total_bids is not None:
                bid_to_cover = total_bids / amount_offered

            cut_off_yield = (
                self._parse_vietnamese_float(cols[idx_ls_trung_thau])
                if idx_ls_trung_thau is not None and idx_ls_trung_thau < len(cols)
                else None
            )
            avg_yield = (
                self._parse_vietnamese_float(cols[idx_ls_danh_nghia])
                if idx_ls_danh_nghia is not None and idx_ls_danh_nghia < len(cols)
                else None
            )
            if avg_yield is None:
                avg_yield = cut_off_yield

            records.append(
                {
                    "date": row_date.isoformat(),
                    "instrument_type": instrument_type,
                    "tenor_label": tenor_label,
                    "tenor_days": tenor_days,
                    "amount_offered": amount_offered,
                    "amount_sold": amount_sold,
                    "bid_to_cover": bid_to_cover,
                    "cut_off_yield": cut_off_yield,
                    "avg_yield": avg_yield,
                    "source": "HNX_AUCTION",
                    "raw_file": raw_file,
                    "fetched_at": now,
                }
            )

        return records

    def _normalize_instrument_type(self, text: str) -> str:
        """
        Normalize Vietnamese instrument type to standard English

        Args:
            text: Vietnamese text

        Returns:
            Normalized instrument type
        """
        text_normalized = text.strip().lower()

        for vn_text, en_text in self.INSTRUMENT_MAP.items():
            if vn_text.lower() in text_normalized:
                return en_text

        return text  # Return original if no match

    def _match_tenor(self, text: str) -> tuple:
        """
        Match Vietnamese tenor text to standardized tenor

        Args:
            text: Vietnamese tenor text

        Returns:
            Tuple of (tenor_label, tenor_days)
        """
        text_normalized = text.strip().lower()

        # Direct match
        for vn_text, (label, days) in self.TENOR_MAP.items():
            if vn_text.lower() in text_normalized or text_normalized in vn_text.lower():
                return (label, days)

        # Pattern matching for numbers
        match = re.search(r'(\d+)\s*(tháng|năm|month|year)', text_normalized, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            unit = match.group(2).lower()

            if unit in ['tháng', 'month']:
                return (f'{value}M', value * 30)
            elif unit in ['năm', 'year']:
                return (f'{value}Y', value * 365)

        # Default to unknown
        return ('Unknown', 0)

    def _parse_tenor_days(self, tenor_text: str) -> int:
        """
        Parse tenor text to get days

        Args:
            tenor_text: Tenor text (e.g., "5Y", "3M")

        Returns:
            Number of days
        """
        if not tenor_text:
            return 0

        tenor_label, tenor_days = self._match_tenor(tenor_text)
        return tenor_days

    def _parse_vietnamese_number(self, text: str) -> Optional[float]:
        """
        Parse Vietnamese number with thousand separators

        Args:
            text: Vietnamese number text

        Returns:
            Parsed number or None
        """
        if not text:
            return None

        try:
            # Remove thousand separators (dots in Vietnamese)
            cleaned = text.replace('.', '').replace(',', '.').strip()
            return float(cleaned) if cleaned else None
        except:
            return None
