"""Loan interest rate parser with Strategy A and B."""

from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup, Tag
import re
from ..utils import (
    normalize_text,
    normalize_bank_name,
    parse_rate_range,
    validate_rate,
    extract_page_updated_text,
    logger
)


class LoanParser:
    """Parser for loan interest rates with fallback strategies."""

    def __init__(self, html_content: str, source_url: str, scraped_at: str):
        """
        Initialize loan parser.

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
        Parse loan rates with auto-fallback strategies.

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

        Parse all <table> elements and identify valid loan tables.

        Returns:
            Tuple of (records, metadata)
        """
        records = []
        tables = self.scoped_soup.find_all('table')

        for table_idx, table in enumerate(tables):
            try:
                # Check if this is a valid loan table
                if not self._is_valid_loan_table(table):
                    continue

                # Parse the table
                table_records = self._parse_loan_table(table)
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

    def _is_valid_loan_table(self, table: Tag) -> bool:
        """
        Check if table is a valid loan table.

        A valid loan table should have:
        - A header row with "Ngân hàng" (Bank)
        - Columns for "Vay tín chấp" and/or "Vay thế chấp"

        Args:
            table: Table element to check

        Returns:
            True if valid loan table
        """
        # Find all header cells
        headers = table.find_all(['th', 'td'])
        header_texts = [normalize_text(h.get_text()) for h in headers]

        # Check for required keywords
        has_bank = any('ngân hàng' in text.lower() for text in header_texts)
        has_loan_type = any(
            'vay tín chấp' in text.lower() or 'vay thế chấp' in text.lower()
            for text in header_texts
        )

        return has_bank and has_loan_type

    def _parse_loan_table(self, table: Tag) -> List[Dict[str, Any]]:
        """
        Parse a single loan table.

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

        # Parse header to find column indices
        header_row = rows[0]
        header_cells = header_row.find_all(['th', 'td'])

        # Find column indices
        bank_col_idx = None
        tin_chap_col_idx = None
        the_chap_col_idx = None

        for i, cell in enumerate(header_cells):
            text = normalize_text(cell.get_text()).lower()
            if 'ngân hàng' in text:
                bank_col_idx = i
            elif 'vay tín chấp' in text:
                tin_chap_col_idx = i
            elif 'vay thế chấp' in text:
                the_chap_col_idx = i

        # If not found in first row, check second row
        if bank_col_idx is None and len(rows) > 1:
            header_row = rows[1]
            header_cells = header_row.find_all(['th', 'td'])
            for i, cell in enumerate(header_cells):
                text = normalize_text(cell.get_text()).lower()
                if 'ngân hàng' in text:
                    bank_col_idx = i
                elif 'vay tín chấp' in text:
                    tin_chap_col_idx = i
                elif 'vay thế chấp' in text:
                    the_chap_col_idx = i

        if bank_col_idx is None:
            return records

        # Determine starting row for data
        data_start_idx = 1 if len(rows) > 1 else 0

        # Parse data rows
        for row in rows[data_start_idx:]:
            cells = row.find_all(['td', 'th'])
            if not cells or len(cells) <= bank_col_idx:
                continue

            # Extract bank name
            bank_name = normalize_bank_name(cells[bank_col_idx].get_text())
            if not bank_name or 'ngân hàng' in bank_name.lower():
                continue

            # Extract tín chấp rate if column exists
            if tin_chap_col_idx is not None and tin_chap_col_idx < len(cells):
                rate_text = normalize_text(cells[tin_chap_col_idx].get_text())
                record = self._create_loan_record(
                    bank_name, 'loan_tin_chap', rate_text
                )
                if record:
                    records.append(record)

            # Extract thế chấp rate if column exists
            if the_chap_col_idx is not None and the_chap_col_idx < len(cells):
                rate_text = normalize_text(cells[the_chap_col_idx].get_text())
                record = self._create_loan_record(
                    bank_name, 'loan_the_chap', rate_text
                )
                if record:
                    records.append(record)

        return records

    def _create_loan_record(self, bank_name: str, series: str,
                           rate_text: str) -> Optional[Dict[str, Any]]:
        """
        Create a loan record from parsed data.

        Args:
            bank_name: Bank name
            series: Loan series (loan_tin_chap or loan_the_chap)
            rate_text: Rate text to parse

        Returns:
            Canonical record or None if parsing fails
        """
        # Parse rate range with new convention
        rate_min_pct, rate_max_pct, rate_pct, parse_warnings = parse_rate_range(rate_text)

        # If min is None, skip this record
        if rate_min_pct is None:
            return None

        return {
            'bank_name': bank_name,
            'product_group': 'loan',
            'series': series,
            'term_label': None,
            'term_months': None,
            'rate_min_pct': rate_min_pct,
            'rate_max_pct': rate_max_pct,
            'rate_pct': rate_pct,
            'raw_value': rate_text,  # Store original value
            'parse_warnings': parse_warnings,  # Store warnings
            'source_url': self.source_url,
            'scraped_at': self.scraped_at,
            'page_updated_text': None  # Will be filled later
        }

    def parse_strategy_b(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Strategy B: Regex/Keyword fallback parser.

        Extracts loan rates using text patterns and keywords.

        Returns:
            Tuple of (records, metadata)
        """
        records = []

        # Look for sections with loan keywords
        sections = self._find_loan_sections()

        for section in sections:
            # Parse each section
            section_records = self._parse_loan_section(section)
            records.extend(section_records)

        metadata = {
            'strategy': 'B',
            'description': 'Regex/Keyword parser',
            'sections_found': len(sections),
            'records_extracted': len(records),
            'reason_fallback': 'Strategy A: No valid tables found'
        }

        return records, metadata

    def _find_loan_sections(self) -> List[Tag]:
        """
        Find sections containing loan rate information.

        Returns:
            List of section elements
        """
        sections = []

        # Look for common section tags
        for tag in ['div', 'section', 'article', 'p', 'li']:
            elements = self.scoped_soup.find_all(tag)
            for elem in elements:
                text = elem.get_text().lower()
                # Check for loan keywords
                if any(keyword in text for keyword in
                      ['vay tín chấp', 'vay thế chấp', 'lãi suất vay']):
                    # Check for rate patterns
                    if re.search(r'\d+[,\.]?\d*\s*%?', text):
                        sections.append(elem)

        return sections

    def _parse_loan_section(self, section: Tag) -> List[Dict[str, Any]]:
        """
        Parse a loan section for rate information.

        Args:
            section: Section element

        Returns:
            List of canonical records
        """
        records = []
        text = section.get_text()

        # Determine loan type from keywords
        is_tin_chap = 'vay tín chấp' in text.lower()
        is_the_chap = 'vay thế chấp' in text.lower()

        if not (is_tin_chap or is_the_chap):
            return records

        # Split into lines for processing
        lines = text.split('\n')

        current_bank = None
        for line in lines:
            line = normalize_text(line)
            if not line:
                continue

            # Check if line looks like a bank name
            if re.match(r'^[A-ZÀ-Ỹ][A-Za-zÀ-Ỹ\s]{2,30}$', line):
                current_bank = line
                continue

            # If we have a bank and the line contains rates
            if current_bank and re.search(r'\d+[,\.]?\d*\s*%?', line):
                # Extract rate
                rate_text = re.search(r'\d+[,\.]?\d*\s*%?\s*(?:[-–]\s*\d+[,\.]?\d*\s*%?)?', line)
                if rate_text:
                    # Create records for both loan types if both keywords present
                    if is_tin_chap:
                        record = self._create_loan_record(
                            current_bank, 'loan_tin_chap', rate_text.group(0)
                        )
                        if record:
                            records.append(record)

                    if is_the_chap:
                        record = self._create_loan_record(
                            current_bank, 'loan_the_chap', rate_text.group(0)
                        )
                        if record:
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
