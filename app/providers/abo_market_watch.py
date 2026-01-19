"""
AsianBondsOnline Market Watch Provider
Fetches Vietnamese bond market data as fallback/validation
"""
import logging
from datetime import date, datetime
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import re

from app.providers.base import BaseProvider, ProviderError, ParseError
from app.config import settings

logger = logging.getLogger(__name__)


class ABOMarketWatchProvider(BaseProvider):
    """
    Provider for AsianBondsOnline Vietnam Market Watch data

    Source: https://asianbondsonline.adb.org/vietnam/

    Provides:
    - Government bond yields (2Y, 5Y, 10Y)
    - VNIBOR (1D, 3M)
    """

    DATE_FORMATS = [
        '%d %b %Y',
        '%d-%b-%Y',
        '%Y-%m-%d',
        '%d/%m/%Y',
    ]

    def __init__(self):
        super().__init__()
        self.vietnam_url = f"{settings.abo_base_url}/vietnam/"

    def fetch(self, target_date: date) -> List[Dict[str, Any]]:
        """
        Fetch market watch data for Vietnam

        Args:
            target_date: Date to fetch data for (not used, ABO shows latest)

        Returns:
            List of market data records (both yields and interbank)
        """
        logger.info(f"Fetching ABO market watch data")

        try:
            # Fetch Vietnam page
            response = self._get(self.vietnam_url)
            self._save_raw(f"abo_vietnam_{target_date.strftime('%Y%m%d')}.html", response.content)

            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract both yields and interbank data
            yield_records = self._parse_yield_table(soup, target_date)
            interbank_records = self._parse_interbank_table(soup, target_date)

            all_records = yield_records + interbank_records

            if not all_records:
                logger.warning(f"No market data found in ABO page")
                return []

            logger.info(f"Found {len(all_records)} ABO market data records")
            return all_records

        except Exception as e:
            logger.error(f"Error fetching ABO market watch: {e}")
            raise ProviderError(f"Failed to fetch ABO market watch: {e}")

    def backfill(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        Backfill ABO market data

        Note: ABO only shows latest data, not historical.

        Args:
            start_date: Not used
            end_date: Not used

        Returns:
            List of latest market data records
        """
        logger.info("ABO backfill: fetching latest available data")
        return self.fetch(date.today())

    def _parse_yield_table(
        self,
        soup: BeautifulSoup,
        data_date: date
    ) -> List[Dict[str, Any]]:
        """
        Parse government bond yield table from ABO

        Args:
            soup: BeautifulSoup object
            data_date: Date for the records

        Returns:
            List of yield curve records
        """
        records = []

        # Look for government bond yield section
        # ABO typically has tables with yields for 2Y, 5Y, 10Y

        tables = soup.find_all('table')

        for table in tables:
            try:
                # Check if table contains yield data
                table_text = table.get_text()
                if not any(keyword in table_text.upper() for keyword in
                          ['GOVT', 'BOND', 'YIELD', '2Y', '5Y', '10Y']):
                    continue

                rows = table.find_all('tr')
                for row in rows[1:]:  # Skip header
                    cols = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]

                    if len(cols) < 2:
                        continue

                    # Look for tenor in first column
                    tenor_text = cols[0]

                    # Map common ABO tenors
                    tenor_info = self._match_abo_tenor(tenor_text)
                    if not tenor_info:
                        continue

                    tenor_label, tenor_days = tenor_info

                    # Extract yield (second column typically)
                    yield_value = self._parse_abo_rate(cols[1])

                    if yield_value is not None:
                        record = {
                            'date': data_date.strftime('%Y-%m-%d'),
                            'tenor_label': tenor_label,
                            'tenor_days': tenor_days,
                            'spot_rate_continuous': yield_value,
                            'par_yield': yield_value,
                            'spot_rate_annual': yield_value,
                            'source': 'ABO',
                            'fetched_at': datetime.now().isoformat()
                        }

                        records.append(record)

                if records:
                    break

            except Exception as e:
                logger.debug(f"Error parsing yield table: {e}")
                continue

        return records

    def _parse_interbank_table(
        self,
        soup: BeautifulSoup,
        data_date: date
    ) -> List[Dict[str, Any]]:
        """
        Parse VNIBOR interbank rate table from ABO

        Args:
            soup: BeautifulSoup object
            data_date: Date for the records

        Returns:
            List of interbank rate records
        """
        records = []

        # Look for VNIBOR section
        tables = soup.find_all('table')

        for table in tables:
            try:
                # Check if table contains interbank data
                table_text = table.get_text()
                if not any(keyword in table_text.upper() for keyword in
                          ['VNIBOR', 'INTERBANK', 'OVERNIGHT', '1M', '3M']):
                    continue

                rows = table.find_all('tr')
                for row in rows[1:]:  # Skip header
                    cols = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]

                    if len(cols) < 2:
                        continue

                    # Look for tenor in first column
                    tenor_text = cols[0]

                    # Map ABO interbank tenors
                    tenor_info = self._match_abo_interbank_tenor(tenor_text)
                    if not tenor_info:
                        continue

                    tenor_label, _ = tenor_info

                    # Extract rate (second column typically)
                    rate_value = self._parse_abo_rate(cols[1])

                    if rate_value is not None:
                        record = {
                            'date': data_date.strftime('%Y-%m-%d'),
                            'tenor_label': tenor_label,
                            'rate': rate_value,
                            'source': 'ABO',
                            'fetched_at': datetime.now().isoformat()
                        }

                        records.append(record)

                if records:
                    break

            except Exception as e:
                logger.debug(f"Error parsing interbank table: {e}")
                continue

        return records

    def _parse_abo_rate(self, value: str) -> Optional[float]:
        """
        ABO uses dot-decimal formatting for rates (e.g., "4.141").
        Our generic Vietnamese float parser treats X.XXX as thousands separators,
        which would turn 4.141 into 4141. This method applies a safe override.
        """
        if not value or value.strip() in {"", "-", "N/A", "NA"}:
            return None

        cleaned = value.strip().replace("%", "").strip()

        # Common dot-decimal formats used by ABO: 4.141 or 4.14
        if re.fullmatch(r"\d{1,3}\.\d{1,6}", cleaned):
            try:
                return float(cleaned)
            except ValueError:
                return None

        # Sometimes pages use comma-decimal
        if re.fullmatch(r"\d{1,3},\d{1,6}", cleaned):
            try:
                return float(cleaned.replace(",", "."))
            except ValueError:
                return None

        # Fall back to the generic parser for other formats.
        return self._parse_vietnamese_float(cleaned)

    def _match_abo_tenor(self, text: str) -> Optional[tuple[str, int]]:
        """
        Match ABO government bond tenor

        Args:
            text: Tenor text from ABO

        Returns:
            Tuple of (tenor_label, days) or None
        """
        text_upper = text.strip().upper()

        # Common ABO tenors
        if '2Y' in text_upper or '2 YEAR' in text_upper or '2-YEAR' in text_upper:
            return ('2Y', 730)
        elif '5Y' in text_upper or '5 YEAR' in text_upper or '5-YEAR' in text_upper:
            return ('5Y', 1825)
        elif '10Y' in text_upper or '10 YEAR' in text_upper or '10-YEAR' in text_upper:
            return ('10Y', 3650)
        elif '7Y' in text_upper or '7 YEAR' in text_upper:
            return ('7Y', 2555)
        elif '3Y' in text_upper or '3 YEAR' in text_upper:
            return ('3Y', 1095)

        return None

    def _match_abo_interbank_tenor(self, text: str) -> Optional[tuple[str, int]]:
        """
        Match ABO VNIBOR tenor

        Args:
            text: Tenor text from ABO

        Returns:
            Tuple of (tenor_label, days) or None
        """
        import re
        text_upper = re.sub(r"\s+", " ", text.strip().upper())

        # Common ABO interbank tenors
        if re.search(r"\bO/N\b|\bON\b|\bOVERNIGHT\b", text_upper):
            return ('ON', 0)
        elif '1W' in text_upper or '1 WEEK' in text_upper:
            return ('1W', 7)
        elif '1M' in text_upper or '1 MONTH' in text_upper:
            return ('1M', 30)
        elif '3M' in text_upper or '3 MONTH' in text_upper:
            return ('3M', 90)
        elif '6M' in text_upper or '6 MONTH' in text_upper:
            return ('6M', 180)

        return None
