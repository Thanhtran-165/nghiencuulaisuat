"""Deposit interest rate parser with Strategy A and B."""

from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup, Tag
import re
from ..utils import (
    normalize_text,
    normalize_bank_name,
    parse_rate_range,
    parse_single_rate,
    parse_term_label,
    validate_rate,
    extract_page_updated_text,
    logger
)


class DepositParser:
    """Parser for deposit interest rates with fallback strategies."""

    def __init__(self, html_content: str, source_url: str, scraped_at: str):
        """
        Initialize deposit parser.

        Args:
            html_content: HTML content to parse
            source_url: Source URL for metadata
            scraped_at: Scrape timestamp for metadata
        """
        self.html_content = html_content
        self.source_url = source_url
        self.scraped_at = scraped_at
        self.soup = BeautifulSoup(html_content, 'lxml')
        self.scoped_soup = self._scope_to_main_content()

    def _scope_to_main_content(self) -> BeautifulSoup:
        """
        Scope parsing to main content area (article or content div).

        Returns:
            BeautifulSoup object scoped to main content, or full soup if not found
        """
        # Try to find <article> tag first
        article = self.soup.find('article')
        if article:
            logger.info("Parser scope: article")
            return BeautifulSoup(str(article), 'lxml')

        # Try to find div with content-related class names
        for class_keyword in ['content', 'post', 'entry', 'main']:
            div = self.soup.find('div', class_=lambda x: x and class_keyword in str(x).lower())
            if div:
                logger.info(f"Parser scope: div.{class_keyword}")
                return BeautifulSoup(str(div), 'lxml')

        # Fallback to full document
        logger.info("Parser scope: document (full page)")
        return self.soup

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
        Strategy A: Table/Header parser.

        Parse all <table> elements and identify valid deposit tables.

        Returns:
            Tuple of (records, metadata)
        """
        records = []
        tables = self.scoped_soup.find_all('table')

        for table_idx, table in enumerate(tables):
            try:
                # Check if this is a valid deposit table
                if not self._is_valid_deposit_table(table):
                    continue

                # Parse the table
                table_records = self._parse_deposit_table(table)
                if table_records:
                    records.extend(table_records)
                    logger.info(f"Parsed table {table_idx}: {len(table_records)} records")

            except Exception as e:
                logger.warning(f"Error parsing table {table_idx}: {e}")
                continue

        metadata = {
            'strategy': 'A',
            'description': 'Table/Header parser',
            'tables_found': len(tables),
            'records_extracted': len(records)
        }

        return records, metadata

    def _is_valid_deposit_table(self, table: Tag) -> bool:
        """
        Check if table is a valid deposit table.

        A valid deposit table should have:
        - A header row with "Ngân hàng" (Bank)
        - Multiple tenor columns (1 tháng, 3 tháng, 6 tháng, etc.)

        Args:
            table: Table element to check

        Returns:
            True if valid deposit table
        """
        # Find all header cells
        headers = table.find_all(['th', 'td'])
        header_texts = [normalize_text(h.get_text()) for h in headers]

        # Check for required keywords
        has_bank = any('ngân hàng' in text.lower() for text in header_texts)
        has_tenor = any(re.search(r'\d+\s*(tháng|tuần)', text, re.IGNORECASE)
                       for text in header_texts)

        return has_bank and has_tenor

    def _parse_deposit_table(self, table: Tag) -> List[Dict[str, Any]]:
        """
        Parse a single deposit table.

        Args:
            table: Table element

        Returns:
            List of canonical records
        """
        records = []

        # Find all rows
        rows = table.find_all('tr')
        if not rows:
            return records

        # Parse header to get series and terms
        header_row = rows[0]
        header_cells = header_row.find_all(['th', 'td'])

        # Determine series type (tai_quay or online) from header context
        series = self._determine_deposit_series(table)

        # Parse tenor columns
        term_columns = []
        for i, cell in enumerate(header_cells):
            text = normalize_text(cell.get_text())
            term_match = re.search(r'(\d+)\s*(tháng|tuần|ngày)', text, re.IGNORECASE)
            if term_match:
                term_label, term_months = parse_term_label(text)
                if term_months is not None:
                    term_columns.append({
                        'index': i,
                        'label': term_label,
                        'months': term_months
                    })

        # If no term columns found, try next row as header
        if not term_columns and len(rows) > 1:
            header_row = rows[1]
            header_cells = header_row.find_all(['th', 'td'])
            for i, cell in enumerate(header_cells):
                text = normalize_text(cell.get_text())
                term_match = re.search(r'(\d+)\s*(tháng|tuần|ngày)', text, re.IGNORECASE)
                if term_match:
                    term_label, term_months = parse_term_label(text)
                    if term_months is not None:
                        term_columns.append({
                            'index': i,
                            'label': term_label,
                            'months': term_months
                        })

        # Parse data rows
        data_start_idx = 1 if len(rows) > 1 and term_columns else 2

        for row in rows[data_start_idx:]:
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue

            # First cell should be bank name
            bank_name = normalize_bank_name(cells[0].get_text())
            if not bank_name or 'ngân hàng' in bank_name.lower():
                continue

            # Extract rates for each term
            for term_col in term_columns:
                cell_idx = term_col['index']
                if cell_idx >= len(cells):
                    continue

                rate_text = normalize_text(cells[cell_idx].get_text())

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
                        'page_updated_text': None  # Will be filled later
                    }
                    records.append(record)

        return records

    def _determine_deposit_series(self, table: Tag) -> str:
        """
        Determine deposit series (tai_quay or online) from table context.

        Args:
            table: Table element

        Returns:
            Series code (deposit_tai_quay or deposit_online)
        """
        # Look for keywords near the table
        table_parent = table.find_parent()
        if table_parent:
            parent_text = table_parent.get_text().lower()
            if 'online' in parent_text or 'trực tuyến' in parent_text:
                return 'deposit_online'

        # Default to tai_quay
        return 'deposit_tai_quay'

    def parse_strategy_b(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Strategy B: Regex/Keyword fallback parser.

        Extracts deposit rates using text patterns and keywords.

        Returns:
            Tuple of (records, metadata)
        """
        records = []

        # Look for sections with deposit keywords
        sections = self._find_deposit_sections()

        for section in sections:
            # Parse each section
            section_records = self._parse_deposit_section(section)
            records.extend(section_records)

        metadata = {
            'strategy': 'B',
            'description': 'Regex/Keyword parser',
            'sections_found': len(sections),
            'records_extracted': len(records),
            'reason_fallback': 'Strategy A: No valid tables found'
        }

        return records, metadata

    def _find_deposit_sections(self) -> List[Tag]:
        """
        Find sections containing deposit rate information.

        Returns:
            List of section elements
        """
        sections = []

        # Look for common section tags
        for tag in ['div', 'section', 'article', 'p']:
            elements = self.scoped_soup.find_all(tag)
            for elem in elements:
                text = elem.get_text().lower()
                # Check for deposit keywords
                if any(keyword in text for keyword in
                      ['tiết kiệm', 'gửi tiết kiệm', 'lãi suất', 'tháng', 'năm']):
                    # Check for rate patterns
                    if re.search(r'\d+[,\.]?\d*\s*%?', text):
                        sections.append(elem)

        return sections

    def _parse_deposit_section(self, section: Tag) -> List[Dict[str, Any]]:
        """
        Parse a deposit section for rate information.

        Args:
            section: Section element

        Returns:
            List of canonical records
        """
        records = []
        text = section.get_text()

        # Determine series type
        series = 'deposit_online' if 'online' in text.lower() else 'deposit_tai_quay'

        # Look for bank names followed by rates
        # Pattern: Bank name + rates for different terms
        lines = text.split('\n')

        current_bank = None
        for line in lines:
            line = normalize_text(line)
            if not line:
                continue

            # Check if line looks like a bank name
            # Bank names typically start with capital letters and don't have many numbers
            if re.match(r'^[A-ZÀ-Ỹ][A-Za-zÀ-Ỹ\s]{2,30}$', line):
                current_bank = line
                continue

            # If we have a bank and the line contains rates
            if current_bank and re.search(r'\d+[,\.]?\d*\s*%?', line):
                # Extract term and rate
                term_match = re.search(r'(\d+)\s*(tháng|tuần|ngày)', line, re.IGNORECASE)
                rate_match = re.search(r'(\d+[,\.]?\d*)\s*%?', line)

                if term_match and rate_match:
                    term_label, term_months = parse_term_label(line)
                    rate_pct = parse_single_rate(rate_match.group(1))
                    rate_pct = validate_rate(rate_pct)

                    if rate_pct is not None and term_months is not None:
                        record = {
                            'bank_name': current_bank,
                            'product_group': 'deposit',
                            'series': series,
                            'term_label': term_label,
                            'term_months': term_months,
                            'rate_min_pct': rate_pct,
                            'rate_max_pct': rate_pct,
                            'rate_pct': rate_pct,
                            'source_url': self.source_url,
                            'scraped_at': self.scraped_at,
                            'page_updated_text': None
                        }
                        records.append(record)

        return records

    def extract_metadata(self) -> Dict[str, Any]:
        """
        Extract page metadata.

        Returns:
            Metadata dictionary
        """
        page_updated_text = extract_page_updated_text(self.html_content)

        return {
            'page_updated_text': page_updated_text
        }
