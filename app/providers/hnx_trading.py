"""
HNX Secondary Trading Provider
Fetches secondary market trading statistics from HNX website

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
from app.normalization.secondary import normalize_segment, normalize_bucket

logger = logging.getLogger(__name__)


class HNXTradingProvider(BaseProvider):
    """
    Provider for HNX Secondary Market Trading Statistics

    Source: https://hnx.vn/thong-ke-thi-truong-trai-phieu.html

    Capability Flags:
    - supports_historical: TBD (after discovery)
    - supports_yesterday: TBD (after discovery)
    - supports_range_backfill: TBD (after discovery)

    Strategy: TBD (depends on endpoint discovery)
    """

    # Segment mappings (Vietnamese to English)
    SEGMENT_MAP = {
        'Trái phiếu chính phủ': 'Government Bond',
        'TP Kho bạc': 'T-Bill',
        'Trái phiếu doanh nghiệp': 'Corporate Bond',
        'TP Doanh nghiệp': 'Corporate Bond',
    }

    # Bucket mappings (investor types)
    BUCKET_MAP = {
        'Tổ chức tín dụng': 'Credit Institution',
        'Doanh nghiệp': 'Enterprise',
        'Cá nhân': 'Individual',
        'Nước ngoài': 'Foreign',
        'Khác': 'Other',
    }

    def __init__(self):
        super().__init__()
        # Daily trading results page (renders via internal POST endpoints)
        self.trading_url = f"{settings.hnx_base_url}/vi-vn/trai-phieu/ket-qua-gd-trong-ngay.html"
        self.trading_module_base = f"{settings.hnx_base_url}/ModuleReportBonds/Bond_KQGD_TrongNgay"

        # Capability flags (confirmed via internal POST endpoints)
        self.supports_historical = True
        self.supports_yesterday = True
        self.supports_range_backfill = True

        # Discovered endpoints
        self.discovered_endpoints = {}

    def discover_endpoints(self) -> Dict[str, Any]:
        """
        Use Playwright to discover JSON/XHR endpoints for trading statistics

        Returns:
            Dictionary with discovery results
        """
        logger.info("Running HNX Trading endpoint discovery...")

        discovery_result = {
            'provider': 'HNXTradingProvider',
            'url': self.trading_url,
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
                    if any(pattern in url.lower() for pattern in ['.json', '/api/', '/ajax/', 'trading', 'thong-ke']):
                        discovery_result['json_endpoints_found'].append(request_info)

                    all_requests.append(request_info)

                page.on('request', handle_request)

                # Navigate to trading statistics page
                logger.info(f"Navigating to {self.trading_url}")
                page.goto(self.trading_url, timeout=settings.playwright_timeout, wait_until='networkidle')

                # Wait for page to fully load
                page.wait_for_load_state('networkidle', timeout=10000)
                page.wait_for_timeout(2000)

                # Try to interact with date pickers or filters
                try:
                    date_inputs = page.query_selector_all('input[type="date"], input[type="text"][placeholder*="ngày"], input[placeholder*="date"]')

                    if date_inputs:
                        logger.info(f"Found {len(date_inputs)} date input fields")

                        for date_input in date_inputs[:1]:
                            try:
                                date_input.click()
                                page.wait_for_timeout(500)
                            except:
                                pass

                    # Look for filter buttons
                    search_buttons = page.query_selector_all('button[type="submit"], button:has-text("Tìm"), button:has-text("Lọc")')

                    if search_buttons:
                        logger.info(f"Found {len(search_buttons)} search/filter buttons")
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

                # Look for pagination
                pagination = page.query_selector_all('button:has-text("Load"), a:has-text("Tiếp"), a:has-text("Next")')
                if pagination:
                    logger.info(f"Found {len(pagination)} pagination/load more elements")
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

            if 'trading' in url or 'thong-ke' in url:
                discovery_result['has_api_endpoint'] = True

        if discovery_result['api_endpoints_to_test']:
            discovery_result['recommendation'] = 'historical_supported'
        elif json_endpoints:
            discovery_result['recommendation'] = 'api_test_required'
        else:
            discovery_result['recommendation'] = 'dom_scrape_fallback'

    def fetch(self, target_date: date) -> List[Dict[str, Any]]:
        """
        Fetch trading statistics for a specific date

        Args:
            target_date: Date to fetch data for

        Returns:
            List of trading statistic records
        """
        logger.info(f"Fetching HNX secondary trading for {target_date}")

        segments = {
            "Outright": "GetTradingOutRightInDay",
            "Repo": "GetTradingReposInDay",
            "SaleAndRepurchase": "GetTradingSaleAndRepurchaseInDay",
            "Loan": "GetTradingLoanInDay",
        }

        all_records: list[dict] = []
        for segment, action in segments.items():
            try:
                rows, raw_file, bucket_context = self._fetch_segment_rows(action=action, target_date=target_date)
            except Exception as e:
                logger.warning(f"HNX trading segment {segment} failed: {e}")
                continue

            bucket_rollup = self._aggregate_trading_rows(rows=rows, expected_bddg=target_date)
            fetched_at = datetime.now().isoformat()
            segment_kind, segment_code = normalize_segment(segment)

            for bucket_label, agg in bucket_rollup.items():
                bucket_kind, bucket_code, bucket_display = normalize_bucket(
                    bucket_label,
                    bucket_context=bucket_context,
                )
                all_records.append(
                    {
                        "date": target_date.isoformat(),
                        "segment": segment,
                        "bucket_label": bucket_label,
                        "segment_kind": segment_kind,
                        "segment_code": segment_code,
                        "bucket_kind": bucket_kind,
                        "bucket_code": bucket_code,
                        "bucket_display": bucket_display,
                        "volume": agg.get("volume"),
                        "value": agg.get("value"),
                        "avg_yield": agg.get("avg_yield"),
                        "source": "HNX_TRADING",
                        "raw_file": raw_file,
                        "fetched_at": fetched_at,
                    }
                )

        logger.info(f"Built {len(all_records)} HNX trading aggregates for {target_date}")
        return all_records

    def _fetch_from_api(self, target_date: date, discovery: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Fetch trading data from discovered API endpoints

        Args:
            target_date: Date to fetch
            discovery: Discovery results with endpoint info

        Returns:
            List of trading records
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
            List of trading records
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
            Parsed trading record or None
        """
        try:
            record = {
                'date': target_date.strftime('%Y-%m-%d'),
                'segment': self._normalize_segment(item.get('segment', item.get('instrumentType', ''))),
                'bucket_label': self._normalize_bucket(item.get('bucket', item.get('investorType', ''))),
                'volume': self._parse_vietnamese_number(item.get('volume', item.get('tradingVolume', ''))),
                'value': self._parse_vietnamese_number(item.get('value', item.get('tradingValue', ''))),
                'avg_yield': self._parse_vietnamese_float(item.get('avgYield', item.get('averageYield', ''))),
                'source': 'HNX_TRADING',
                'raw_file': json.dumps(item),
                'fetched_at': datetime.now().isoformat()
            }

            return record

        except Exception as e:
            logger.debug(f"Error parsing API record: {e}")
            return None

    def _fetch_from_dom(self, target_date: date) -> List[Dict[str, Any]]:
        """
        Fetch trading data by scraping DOM

        Args:
            target_date: Date to fetch

        Returns:
            List of trading records
        """
        try:
            response = self._get(self.trading_url)
            self._save_raw(f"trading_{target_date.strftime('%Y%m%d')}.html", response.content)

            soup = BeautifulSoup(response.content, 'html.parser')
            records = self._parse_trading_table(soup, target_date)

            if records:
                logger.info(f"Parsed {len(records)} records from DOM")
            else:
                logger.warning(f"No trading data found for {target_date}")

            return records

        except Exception as e:
            logger.error(f"Error fetching from DOM: {e}")
            raise ProviderError(f"Failed to fetch trading data: {e}")

    def _parse_trading_table(self, soup: BeautifulSoup, data_date: date) -> List[Dict[str, Any]]:
        """
        Parse trading statistics table from HTML

        Args:
            soup: BeautifulSoup object
            data_date: Date of the data

        Returns:
            List of trading records
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

                # Look for trading-related keywords
                if not any(keyword in ' '.join(headers).lower() for keyword in
                          ['khối lượng', 'volume', 'giá trị', 'value', 'lợi suất', 'yield', 'thống kê']):
                    continue

                logger.debug(f"Table {table_idx}: headers = {headers}")

                for row in rows[1:]:
                    cols = [td.get_text(strip=True) for td in row.find_all('td')]

                    if not cols or len(cols) < 3:
                        continue

                    record = self._parse_trading_row(cols, data_date)
                    if record:
                        records.append(record)

                if records:
                    logger.info(f"Parsed {len(records)} records from table {table_idx}")
                    break

            except Exception as e:
                logger.debug(f"Error parsing table {table_idx}: {e}")
                continue

        return records

    def _parse_trading_row(self, cols: List[str], data_date: date) -> Optional[Dict[str, Any]]:
        """
        Parse a single trading table row

        Args:
            cols: List of column values
            data_date: Date of the data

        Returns:
            Trading record or None
        """
        try:
            segment = self._normalize_segment(cols[0]) if len(cols) > 0 else ''
            bucket_label = self._normalize_bucket(cols[1]) if len(cols) > 1 else ''
            volume = self._parse_vietnamese_number(cols[2]) if len(cols) > 2 else None
            value = self._parse_vietnamese_number(cols[3]) if len(cols) > 3 else None
            avg_yield = self._parse_vietnamese_float(cols[4]) if len(cols) > 4 else None

            if not segment or not bucket_label:
                return None

            record = {
                'date': data_date.strftime('%Y-%m-%d'),
                'segment': segment,
                'bucket_label': bucket_label,
                'volume': volume,
                'value': value,
                'avg_yield': avg_yield,
                'source': 'HNX_TRADING',
                'raw_file': '|'.join(cols),
                'fetched_at': datetime.now().isoformat()
            }

            return record

        except Exception as e:
            logger.debug(f"Error parsing trading row: {e}")
            return None

    def backfill(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        Backfill trading statistics for a date range

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            List of all trading records in range

        Raises:
            NotSupportedError: If historical access not available
        """
        logger.info(f"Backfilling trading statistics from {start_date} to {end_date}")

        all_records = []
        current_date = start_date

        while current_date <= end_date:
            logger.info(f"Fetching trading statistics for {current_date}")
            try:
                records = self.fetch(current_date)
                all_records.extend(records)
            except Exception as e:
                logger.error(f"Failed to fetch {current_date}: {e}")

            if settings.rate_limit_seconds and settings.rate_limit_seconds > 0:
                time.sleep(float(settings.rate_limit_seconds))
            current_date += timedelta(days=1)

        logger.info(f"Backfill complete: {len(all_records)} total records")
        return all_records

    def _fetch_segment_rows(self, action: str, target_date: date) -> tuple[list[dict], Optional[str], Optional[str]]:
        """
        Fetch raw (row-level) trades for a segment action and date, across all pages.

        HNX expects a `p_keysearch` format: `dd/mm/YYYY|`.
        """
        url = f"{self.trading_module_base}/{action}"
        keysearch = f"{target_date.strftime('%d/%m/%Y')}|"

        rows: list[dict] = []
        raw_file: Optional[str] = None
        bucket_context: Optional[str] = None

        per_page = 50
        total_pages: Optional[int] = None

        for page in range(1, 200):  # hard cap safety
            resp = self._post(
                url,
                data={
                    "p_keysearch": keysearch,
                    "pColOrder": "col_c",
                    "pOrderType": "ASC",
                    "pCurrentPage": page,
                    "pRecordOnPage": per_page,
                    "pIsSearch": 1,
                    "pIsChangeTab": 0,
                },
            )

            if raw_file is None:
                saved = self._save_raw(
                    f"hnx_trading_{action}_{target_date.strftime('%Y%m%d')}_p{page}.html",
                    resp.content,
                )
                raw_file = str(saved) if saved else None

            soup = BeautifulSoup(resp.content, "html.parser")
            page_rows, page_bucket_context = self._parse_trading_table_rows(soup)
            if bucket_context is None and page_bucket_context:
                bucket_context = page_bucket_context
            rows.extend(page_rows)

            if total_pages is None:
                total = self._parse_total_records(resp.text)
                if total is not None:
                    total_pages = max(1, (total + per_page - 1) // per_page)

            if total_pages is not None and page >= total_pages:
                break

            if total_pages is None and not page_rows:
                break

        return rows, raw_file, bucket_context

    def _parse_total_records(self, html_text: str) -> Optional[int]:
        m = re.search(r"Tổng số\\s+(\\d+)\\s+bản ghi", html_text)
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:
            return None

    def _parse_trading_table_rows(self, soup: BeautifulSoup) -> tuple[list[dict], Optional[str]]:
        table = soup.find("table", id="_tableDatas")
        if not table:
            return [], None

        headers = [th.get_text(" ", strip=True).casefold() for th in table.select("thead th")]

        def find_idx(*needles: str) -> Optional[int]:
            for i, h in enumerate(headers):
                if any(n in h for n in needles):
                    return i
            return None

        idx_bddg = find_idx("ngày bđgd", "ngay bđgd")
        idx_bucket = find_idx("kỳ hạn còn lại", "kỳ hạn mbl", "kh giao dịch", "kh vay")
        idx_yield = find_idx("lợi suất", "lãi suất")
        idx_volume = find_idx("klgd")
        idx_value = find_idx("gtgd theo mệnh giá", "gtgd (đồng)", "gtgd", "giá trị")

        if idx_bddg is None or idx_bucket is None:
            return [], None

        bucket_context: Optional[str] = None
        bucket_header = headers[idx_bucket] if idx_bucket < len(headers) else ""
        if "kỳ hạn còn lại" in bucket_header or "ky han con lai" in bucket_header:
            bucket_context = "remaining_maturity"
        elif "kỳ hạn mbl" in bucket_header or "ky han mbl" in bucket_header:
            bucket_context = "mbl_maturity"
        elif "kh giao dịch" in bucket_header:
            bucket_context = "counterparty"
        elif "kh vay" in bucket_header:
            bucket_context = "loan_counterparty"

        out: list[dict] = []
        for tr in table.select("tbody tr"):
            cols = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if idx_bddg >= len(cols) or idx_bucket >= len(cols):
                continue

            bddg_str = cols[idx_bddg]
            try:
                bddg = datetime.strptime(bddg_str, "%d/%m/%Y").date()
            except Exception:
                continue

            bucket = cols[idx_bucket].strip()
            if not bucket:
                continue

            yld = (
                self._parse_vietnamese_float(cols[idx_yield])
                if idx_yield is not None and idx_yield < len(cols)
                else None
            )
            vol = (
                self._parse_vietnamese_float(cols[idx_volume])
                if idx_volume is not None and idx_volume < len(cols)
                else None
            )
            val = (
                self._parse_vietnamese_float(cols[idx_value])
                if idx_value is not None and idx_value < len(cols)
                else None
            )

            out.append({"bddg": bddg, "bucket": bucket, "yield": yld, "volume": vol, "value": val})

        return out, bucket_context

    def _aggregate_trading_rows(self, rows: list[dict], expected_bddg: date) -> dict[str, dict]:
        """
        Aggregate row-level trades to segment+bucket totals.

        - volume: sum of `volume` where present
        - value: sum of `value` where present
        - avg_yield: value-weighted average where possible
        """
        buckets: dict[str, dict] = {}
        for r in rows:
            if r.get("bddg") != expected_bddg:
                continue

            bucket = r.get("bucket")
            if not bucket:
                continue

            agg = buckets.setdefault(
                bucket,
                {"volume": 0.0, "value": 0.0, "_yield_num": 0.0, "_yield_den": 0.0},
            )

            vol = r.get("volume")
            if isinstance(vol, (int, float)):
                agg["volume"] += float(vol)

            val = r.get("value")
            if isinstance(val, (int, float)):
                agg["value"] += float(val)

            yld = r.get("yield")
            if isinstance(yld, (int, float)) and isinstance(val, (int, float)) and float(val) > 0:
                agg["_yield_num"] += float(yld) * float(val)
                agg["_yield_den"] += float(val)

        finalized: dict[str, dict] = {}
        for bucket, agg in buckets.items():
            avg_yield = None
            if agg["_yield_den"] > 0:
                avg_yield = agg["_yield_num"] / agg["_yield_den"]

            volume = agg["volume"] if agg["volume"] != 0.0 else None
            value = agg["value"] if agg["value"] != 0.0 else None

            finalized[bucket] = {"volume": volume, "value": value, "avg_yield": avg_yield}

        return finalized

    def _normalize_segment(self, text: str) -> str:
        """
        Normalize Vietnamese segment to standard English

        Args:
            text: Vietnamese text

        Returns:
            Normalized segment
        """
        text_normalized = text.strip().lower()

        for vn_text, en_text in self.SEGMENT_MAP.items():
            if vn_text.lower() in text_normalized:
                return en_text

        return text

    def _normalize_bucket(self, text: str) -> str:
        """
        Normalize Vietnamese bucket/investor type to standard English

        Args:
            text: Vietnamese text

        Returns:
            Normalized bucket
        """
        text_normalized = text.strip().lower()

        for vn_text, en_text in self.BUCKET_MAP.items():
            if vn_text.lower() in text_normalized:
                return en_text

        return text

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
            cleaned = text.replace('.', '').replace(',', '.').strip()
            return float(cleaned) if cleaned else None
        except:
            return None
