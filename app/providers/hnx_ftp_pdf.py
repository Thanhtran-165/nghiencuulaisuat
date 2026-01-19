"""
HNX FTP PDF Provider
Fetches yield change statistics from HNX FTP server
"""
import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import io
import re

try:
    import camelot
    CAMELOT_AVAILABLE = True
except ImportError:
    CAMELOT_AVAILABLE = False

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

from app.providers.base import BaseProvider, ProviderError, ParseError
from app.config import settings

logger = logging.getLogger(__name__)


class HNXFTPPDFProvider(BaseProvider):
    """
    Provider for HNX FTP PDF Yield Change Statistics

    Source pattern:
    https://owa.hnx.vn/ftp///THONGKEGIAODICH//YYYYMMDD/TP/YYYYMMDD_TP_Yield_change_statistics.pdf
    """

    DATE_FORMATS = [
        '%d/%m/%Y',
        '%Y-%m-%d',
        '%d-%m-%Y',
        '%d.%m.%Y',
    ]

    def __init__(self):
        super().__init__()
        self.base_url = settings.hnx_ftp_base_url

    def fetch(self, target_date: date) -> List[Dict[str, Any]]:
        """
        Fetch yield change statistics PDF for a specific date

        Args:
            target_date: Date to fetch data for

        Returns:
            List of yield change statistics records
        """
        logger.info(f"Fetching HNX FTP PDF for {target_date}")

        # Construct PDF URL
        date_str = target_date.strftime('%Y%m%d')
        pdf_url = f"{self.base_url}/THONGKEGIAODICH/{date_str}/TP/{date_str}_TP_Yield_change_statistics.pdf"

        try:
            # Try to download PDF
            response = self._get(pdf_url)

            # Save raw PDF
            raw_file = self._save_raw(
                f"yield_change_{target_date.strftime('%Y%m%d')}.pdf",
                response.content
            )

            # Parse PDF
            records = self._parse_pdf(response.content, target_date, raw_file)

            if not records:
                logger.warning(f"No yield change statistics found in PDF for {target_date}")
                return []

            logger.info(f"Found {len(records)} yield change statistics records for {target_date}")
            return records

        except Exception as e:
            logger.warning(f"Failed to fetch PDF for {target_date}: {e}")
            # Return empty list (PDF may not exist for this date)
            return []

    def backfill(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        Backfill yield change statistics for a date range

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of all yield change statistics records
        """
        logger.info(f"Backfilling HNX FTP PDFs from {start_date} to {end_date}")

        all_records = []
        current_date = start_date

        while current_date <= end_date:
            try:
                records = self.fetch(current_date)
                all_records.extend(records)
            except Exception as e:
                logger.debug(f"Skipping {current_date}: {e}")

            current_date += timedelta(days=1)

        logger.info(f"Backfill complete: {len(all_records)} total records")
        return all_records

    def _parse_pdf(
        self,
        pdf_content: bytes,
        data_date: date,
        raw_file: Optional[Path]
    ) -> List[Dict[str, Any]]:
        """
        Parse yield change statistics from PDF content

        Args:
            pdf_content: PDF file content
            data_date: Date of the data
            raw_file: Path to saved raw file

        Returns:
            List of parsed records
        """
        records = []

        # Try camelot first (better for tables)
        if CAMELOT_AVAILABLE:
            try:
                records = self._parse_with_camelot(pdf_content, data_date, raw_file)
                if records:
                    return records
            except Exception as e:
                logger.debug(f"Camelot parsing failed: {e}")

        # Fallback to pdfplumber
        if PDFPLUMBER_AVAILABLE:
            try:
                records = self._parse_with_pdfplumber(pdf_content, data_date, raw_file)
                if records:
                    return records
            except Exception as e:
                logger.debug(f"pdfplumber parsing failed: {e}")

        logger.warning("Both PDF parsers failed or returned no data")
        return []

    def _parse_with_camelot(
        self,
        pdf_content: bytes,
        data_date: date,
        raw_file: Optional[Path]
    ) -> List[Dict[str, Any]]:
        """Parse PDF using camelot"""
        records = []

        try:
            # Create PDF file object from bytes
            pdf_file = io.BytesIO(pdf_content)

            # Extract tables
            tables = camelot.read_pdf(pdf_file, pages='all', flavor='lattice')

            logger.info(f"Camelot found {len(tables)} tables")

            for table_idx, table in enumerate(tables):
                df = table.df

                # Skip empty tables
                if df.empty:
                    continue

                # Try to parse as yield change statistics
                parsed = self._parse_yield_change_df(df, data_date, raw_file)
                records.extend(parsed)

            return records

        except Exception as e:
            logger.error(f"Error parsing PDF with camelot: {e}")
            raise ParseError(f"Camelot parsing failed: {e}")

    def _parse_with_pdfplumber(
        self,
        pdf_content: bytes,
        data_date: date,
        raw_file: Optional[Path]
    ) -> List[Dict[str, Any]]:
        """Parse PDF using pdfplumber"""
        records = []

        try:
            pdf_file = io.BytesIO(pdf_content)

            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()

                    for table in tables:
                        if not table or len(table) < 2:
                            continue

                        # Convert to DataFrame-like structure
                        df_data = []
                        for row in table:
                            df_data.append([str(cell) if cell is not None else '' for cell in row])

                        # Try to parse
                        parsed = self._parse_yield_change_table(df_data, data_date, raw_file)
                        records.extend(parsed)

            return records

        except Exception as e:
            logger.error(f"Error parsing PDF with pdfplumber: {e}")
            raise ParseError(f"pdfplumber parsing failed: {e}")

    def _parse_yield_change_df(self, df, data_date: date, raw_file: Optional[Path]) -> List[Dict[str, Any]]:
        """
        Parse DataFrame as yield change statistics

        This is a placeholder - actual implementation depends on PDF structure
        """
        records = []

        # Example parsing logic (adjust based on actual PDF structure)
        # This would need to be adapted to the actual HNX PDF format

        for idx, row in df.iterrows():
            # Skip header rows
            if idx < 1:
                continue

            # Extract data from row
            # This is just example logic - adjust based on actual structure
            bucket_label = str(row.iloc[0]) if len(row) > 0 else None
            volume_domestic = self._parse_vietnamese_float(str(row.iloc[1])) if len(row) > 1 else None

            if bucket_label:
                record = {
                    'date': data_date.strftime('%Y-%m-%d'),
                    'bucket_label': bucket_label,
                    'currency': 'VND',
                    'volume_domestic': volume_domestic,
                    'volume_foreign': None,
                    'weight_domestic': None,
                    'weight_foreign': None,
                    'yield_min_domestic': None,
                    'yield_max_domestic': None,
                    'yield_min_foreign': None,
                    'yield_max_foreign': None,
                    'source': 'HNX_FTP_PDF',
                    'raw_file': str(raw_file) if raw_file else None
                }

                records.append(record)

        return records

    def _parse_number_en(self, value: Optional[str]) -> Optional[float]:
        """
        Parse English-formatted numbers from HNX PDF tables.

        Examples:
          - "1,000,000" -> 1000000.0
          - "0.01" -> 0.01
          - "-" -> None
        """
        if value is None:
            return None
        text = str(value).strip()
        if not text or text in {"-", "N/A", "NA"}:
            return None

        # Remove whitespace/newlines.
        text = re.sub(r"\s+", "", text)

        # Common case: thousands separators with commas.
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", text):
            text = text.replace(",", "")
            try:
                return float(text)
            except ValueError:
                return None

        # Fallback: plain float/int (dot decimal).
        try:
            return float(text)
        except ValueError:
            return None

    def _parse_range_en(self, value: Optional[str]) -> tuple[Optional[float], Optional[float]]:
        """
        Parse yield range strings like "1.7939 - 1.7958".
        """
        if value is None:
            return None, None
        text = str(value).strip()
        if not text or text in {"-", "N/A", "NA"}:
            return None, None

        # Normalize unicode dashes.
        text = text.replace("–", "-").replace("—", "-")
        parts = [p.strip() for p in text.split("-") if p.strip()]
        if len(parts) == 1:
            v = self._parse_number_en(parts[0])
            return v, v
        if len(parts) >= 2:
            return self._parse_number_en(parts[0]), self._parse_number_en(parts[1])
        return None, None

    def _parse_yield_change_table(
        self,
        table_data: List[List[str]],
        data_date: date,
        raw_file: Optional[Path]
    ) -> List[Dict[str, Any]]:
        """
        Parse table data as yield change statistics

        Expected structure (pdfplumber extracted):
          [0] Remaining maturity
          [1] Currency
          [2] Volume Domestic
          [3] Volume Foreign
          [4] Weight Domestic
          [5] Weight Foreign
          [6] Yield range Domestic (min-max)
          [7] Yield range Foreign (min-max)
        """
        records = []

        if not table_data or len(table_data) < 3:
            return records

        # Find the header row that contains "Remaining maturity".
        header_idx = None
        for i, row in enumerate(table_data[:5]):
            row_text = " ".join(str(c or "") for c in row).lower()
            if "remaining" in row_text and "maturity" in row_text and "yield" in row_text:
                header_idx = i
                break

        if header_idx is None:
            return records

        now = datetime.now().isoformat()
        for row in table_data[header_idx + 2:]:  # skip main header + subheader
            if not row or len(row) < 4:
                continue

            bucket_label = str(row[0] or "").strip()
            if not bucket_label or bucket_label.lower() in {"remaining maturity"}:
                continue

            currency = str(row[1] or "").replace("\n", "").strip() or "VND"

            volume_domestic = self._parse_number_en(row[2] if len(row) > 2 else None)
            volume_foreign = self._parse_number_en(row[3] if len(row) > 3 else None)
            weight_domestic = self._parse_number_en(row[4] if len(row) > 4 else None)
            weight_foreign = self._parse_number_en(row[5] if len(row) > 5 else None)

            yd_min, yd_max = self._parse_range_en(row[6] if len(row) > 6 else None)
            yf_min, yf_max = self._parse_range_en(row[7] if len(row) > 7 else None)

            records.append(
                {
                    "date": data_date.strftime("%Y-%m-%d"),
                    "bucket_label": bucket_label,
                    "currency": currency,
                    "volume_domestic": volume_domestic,
                    "volume_foreign": volume_foreign,
                    "weight_domestic": weight_domestic,
                    "weight_foreign": weight_foreign,
                    "yield_min_domestic": yd_min,
                    "yield_max_domestic": yd_max,
                    "yield_min_foreign": yf_min,
                    "yield_max_foreign": yf_max,
                    "source": "HNX_FTP_PDF",
                    "raw_file": str(raw_file) if raw_file else None,
                    "fetched_at": now,
                }
            )

        return records
