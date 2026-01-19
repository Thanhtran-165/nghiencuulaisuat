"""Deposit interest rate parser for 24hmoney.vn source.

This source has two separate tables:
- "tại quầy" (offline/in-branch)
- "trực tuyến" (online)

Each table has clear HTML structure with:
- Bank names in <a class="name"> tags
- Rates in <p class="bank-interest-rate"> tags
- Term headers like "01 tháng", "03 tháng", "06 tháng", "12 tháng"""

from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup, Tag
import re
from ..utils import (
    normalize_text,
    normalize_bank_name,
    parse_single_rate,
    parse_term_label,
    validate_rate,
    logger
)


class Deposit24hMoneyParser:
    """Parser for 24hmoney.vn deposit rates with Strategy A and B."""

    def __init__(self, html_content: str, source_url: str, scraped_at: str):
        """
        Initialize 24hmoney deposit parser.

        Args:
            html_content: HTML content to parse
            source_url: Source URL for metadata
            scraped_at: Scrape timestamp for metadata
        """
        self.html_content = html_content
        self.source_url = source_url
        self.scraped_at = scraped_at
        self.soup = BeautifulSoup(html_content, 'lxml')

    def parse(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Parse deposit rates with auto-fallback strategies.

        Returns:
            Tuple of (records, metadata)
            - records: List of canonical record dictionaries
            - metadata: Parsing metadata including strategy used
        """
        # Try Strategy A first (table/header)
        records, metadata = self.parse_strategy_a()

        if records:
            logger.info(f"Strategy A succeeded: extracted {len(records)} records")
            return records, metadata

        # Fallback to Strategy B (regex/keyword)
        logger.warning("Strategy A failed, falling back to Strategy B")
        records, metadata = self.parse_strategy_b()

        if records:
            logger.info(f"Strategy B succeeded: extracted {len(records)} records")
        else:
            logger.error("Both Strategy A and B failed to extract records")

        return records, metadata

    def parse_strategy_a(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Strategy A: Table/Header parser specialized for 24hmoney structure.

        24hmoney has two distinct tables:
        - div.bank-rate-offline table.vue-table.offline-table -> deposit_tai_quay
        - div.bank-rate-online table.vue-table.online-table -> deposit_online

        Returns:
            Tuple of (records, metadata)
        """
        records = []

        # Find offline table (tại quầy)
        offline_table = self.soup.select_one('.bank-rate-offline table')
        if offline_table:
            offline_records = self._parse_24hmoney_table(offline_table, 'deposit_tai_quay')
            records.extend(offline_records)
            logger.info(f"Parsed offline table: {len(offline_records)} records")

        # Find online table (trực tuyến)
        online_table = self.soup.select_one('.bank-rate-online table')
        if online_table:
            online_records = self._parse_24hmoney_table(online_table, 'deposit_online')
            records.extend(online_records)
            logger.info(f"Parsed online table: {len(online_records)} records")

        metadata = {
            'strategy': 'A',
            'description': 'Table/Header parser (24hmoney specialized)',
            'tables_parsed': int(bool(offline_table)) + int(bool(online_table)),
            'records_extracted': len(records)
        }

        return records, metadata

    def _parse_24hmoney_table(self, table: Tag, series: str) -> List[Dict[str, Any]]:
        """
        Parse a single 24hmoney deposit table.

        Args:
            table: Table element
            series: Series code ('deposit_tai_quay' or 'deposit_online')

        Returns:
            List of canonical records
        """
        records = []

        # Find all rows
        rows = table.find_all('tr')
        if not rows:
            return records

        # Parse header to get term columns
        header_row = rows[0]
        header_cells = header_row.find_all(['th', 'td'])

        # Parse tenor columns from header
        term_columns = []
        for i, cell in enumerate(header_cells):
            text = normalize_text(cell.get_text())
            # Match patterns: "01 tháng", "03 tháng", "06 tháng", "09 tháng", "12 tháng"
            term_match = re.search(r'(\d+)\s*(tháng)', text, re.IGNORECASE)
            if term_match:
                term_label, term_months = parse_term_label(text)
                if term_months is not None:
                    term_columns.append({
                        'index': i,
                        'label': term_label,
                        'months': term_months
                    })

        if not term_columns:
            logger.warning(f"No term columns found in header for {series}")
            return records

        # Parse data rows (skip header row)
        for row in rows[1:]:
            # Skip hidden rows (24hmoney uses style="display:none" for pagination)
            row_style = row.get('style', '')
            if 'display:none' in row_style or 'display: none' in row_style:
                continue

            cells = row.find_all(['td', 'th'])
            if not cells or len(cells) < 2:
                continue

            # First cell should contain bank name in <a class="name">
            bank_link = cells[0].find('a', class_='name')
            if not bank_link:
                continue

            bank_name = normalize_bank_name(bank_link.get_text())
            if not bank_name or len(bank_name) < 2:
                continue

            # Extract rates for each term column
            for term_col in term_columns:
                cell_idx = term_col['index']
                if cell_idx >= len(cells):
                    continue

                rate_cell = cells[cell_idx]
                rate_p = rate_cell.find('p', class_='bank-interest-rate')

                if not rate_p:
                    continue

                rate_text = normalize_text(rate_p.get_text())

                # Skip empty or placeholder values
                if not rate_text or rate_text in ['-', '-', '/', 'N/A']:
                    continue

                # Parse rate
                rate_pct = parse_single_rate(rate_text)
                rate_pct = validate_rate(rate_pct)

                if rate_pct is not None:
                    record = {
                        'bank_name': bank_name,
                        'product_group': 'deposit',
                        'series': series,
                        'term_label': term_col['label'],
                        'term_months': term_col['months'],
                        'rate_min_pct': rate_pct,
                        'rate_max_pct': rate_pct,
                        'rate_pct': rate_pct,
                        'source_url': self.source_url,
                        'scraped_at': self.scraped_at,
                        'page_updated_text': None  # Not available in this format
                    }
                    records.append(record)

        return records

    def parse_strategy_b(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Strategy B: Regex/Keyword fallback parser.

        Fallback Strategy B extracts:
        1. Bank names from <a class="name"> tags in order
        2. Rates from <p class="bank-interest-rate"> tags in order
        3. Infers term mapping from table structure context

        Returns:
            Tuple of (records, metadata)
        """
        records = []

        try:
            # Find all bank links
            bank_links = self.soup.find_all('a', class_='name')
            bank_names = [normalize_bank_name(link.get_text()) for link in bank_links]
            bank_names = [name for name in bank_names if name and len(name) > 2]

            # Find all rate cells
            rate_cells = self.soup.find_all('p', class_='bank-interest-rate')
            rate_values = []
            for cell in rate_cells:
                text = normalize_text(cell.get_text())
                if text and text not in ['-', '', '/', 'N/A']:
                    rate_pct = parse_single_rate(text)
                    rate_pct = validate_rate(rate_pct)
                    if rate_pct is not None:
                        rate_values.append(rate_pct)

            # Try to infer term structure from header cells
            header_cells = self.soup.find_all('th')
            term_months_list = []
            for cell in header_cells:
                text = normalize_text(cell.get_text())
                term_match = re.search(r'(\d+)\s*(tháng)', text, re.IGNORECASE)
                if term_match:
                    _, term_months = parse_term_label(text)
                    if term_months is not None:
                        term_months_list.append(term_months)

            # If we found banks, rates, and terms, map them together
            if bank_names and rate_values and term_months_list:
                # Assume rows are organized by bank, columns by term
                # 24hmoney typically has: 1 month, 3 month, 6 month, 9 month, 12 month
                num_terms = len(term_months_list)

                # Determine series from context (check for "online" or "trực tuyến")
                page_text = self.soup.get_text().lower()
                if 'trực tuyến' in page_text or 'online' in page_text:
                    series_list = ['deposit_online']
                elif 'tại quầy' in page_text or 'offline' in page_text:
                    series_list = ['deposit_tai_quay']
                else:
                    # Use both if context unclear
                    series_list = ['deposit_tai_quay', 'deposit_online']

                # Distribute rates across banks and terms
                # This is a best-effort mapping when table structure is unclear
                rate_idx = 0
                for series in series_list:
                    for bank_name in bank_names:
                        for term_months in term_months_list:
                            if rate_idx < len(rate_values):
                                record = {
                                    'bank_name': bank_name,
                                    'product_group': 'deposit',
                                    'series': series,
                                    'term_label': f"{term_months} tháng",
                                    'term_months': term_months,
                                    'rate_min_pct': rate_values[rate_idx],
                                    'rate_max_pct': rate_values[rate_idx],
                                    'rate_pct': rate_values[rate_idx],
                                    'source_url': self.source_url,
                                    'scraped_at': self.scraped_at,
                                    'page_updated_text': None
                                }
                                records.append(record)
                                rate_idx += 1

        except Exception as e:
            logger.warning(f"Strategy B parsing error: {e}")

        metadata = {
            'strategy': 'B',
            'description': 'Regex/Keyword fallback parser',
            'records_extracted': len(records),
            'warning': 'Strategy B is best-effort mapping and may be inaccurate'
        }

        return records, metadata


def parse_deposit_24hmoney(html_content: str, source_url: str, scraped_at: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Main entry point for parsing 24hmoney deposit rates.

    Args:
        html_content: HTML content to parse
        source_url: Source URL for metadata
        scraped_at: Scrape timestamp for metadata

    Returns:
        Tuple of (records, metadata)
    """
    parser = Deposit24hMoneyParser(html_content, source_url, scraped_at)
    return parser.parse()
