"""Utility functions for bank interest rate scraper."""

import hashlib
import json
import logging
import re
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def compute_content_hash(content: str, *, salt: Optional[str] = None) -> str:
    """
    Compute SHA256 hash of content for change detection.

    Note:
    - We salt by `observed_day` (YYYY-MM-DD) when available so that daily scrapes
      still create a new snapshot even if the source HTML is unchanged.
    - This prevents gaps like "no data on 19/11" when the site content didn't change.

    Args:
        content: The content to hash (HTML or normalized text)
        salt: Optional salt value (e.g., observed_day)

    Returns:
        SHA256 hash as hexadecimal string
    """
    if salt:
        payload = f"{salt}\n{content}"
    else:
        payload = content
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_text(text: str) -> str:
    """
    Normalize whitespace and trim text.

    Args:
        text: The text to normalize

    Returns:
        Normalized text with trimmed and collapsed whitespace
    """
    if not text:
        return ""
    # Replace multiple whitespace characters with single space
    text = re.sub(r'\s+', ' ', text)
    # Trim leading and trailing whitespace
    return text.strip()


def normalize_bank_name(name: str) -> str:
    """
    Normalize bank name.

    Args:
        name: Bank name to normalize

    Returns:
        Normalized bank name
    """
    if not name:
        return ""
    return normalize_text(name)


def parse_rate_range(rate_str: str) -> Tuple[Optional[float], Optional[float], Optional[float], str]:
    """
    Parse rate string into (min, max, pct, warnings_json) tuple.

    Handles various formats:
    - "Từ x" => (x, NULL, NULL, warning)
    - "x–y" or "x-y" => (x, y, NULL, [])
    - "x" => (x, x, x, [])
    - rỗng/"—"/"N/A" => (NULL, NULL, NULL, warning)

    Args:
        rate_str: Rate string to parse

    Returns:
        Tuple of (rate_min_pct, rate_max_pct, rate_pct, warnings_json)
        warnings_json is JSON string of warning list
    """
    warnings: List[str] = []

    if not rate_str:
        warnings.append("empty_value")
        return None, None, None, json.dumps(warnings)

    # Normalize the string
    original_str = rate_str
    rate_str = normalize_text(rate_str)

    # Check for empty-like values after normalization
    if rate_str in ['', '—', '–', '-', 'N/A', 'n/a', 'NA']:
        warnings.append(f"invalid_value_{original_str[:20]}")
        return None, None, None, json.dumps(warnings)

    # Check for "Từ" prefix - special case for loan rates
    from_match = re.match(r'^Từ\s+', rate_str, re.IGNORECASE)
    if from_match:
        # Remove "Từ" and extract the number
        rate_str = re.sub(r'^Từ\s+', '', rate_str, flags=re.IGNORECASE)
        single_match = re.search(r'^([\d.,]+)', rate_str)
        if single_match:
            min_rate = parse_single_rate(single_match.group(1))
            min_rate = validate_rate(min_rate)
            warnings.append("from_prefix_no_max")
            # "Từ x" => min=x, max=NULL, pct=NULL
            return min_rate, None, None, json.dumps(warnings)
        else:
            warnings.append("from_prefix_no_value")
            return None, None, None, json.dumps(warnings)

    # Try to match range patterns "a - b" or "a – b"
    range_match = re.search(r'^([\d.,]+)\s*[-–]\s*([\d.,]+)', rate_str)
    if range_match:
        min_str, max_str = range_match.groups()
        min_rate = parse_single_rate(min_str)
        max_rate = parse_single_rate(max_str)
        min_rate = validate_rate(min_rate)
        max_rate = validate_rate(max_rate)

        if min_rate is not None and max_rate is not None:
            # Range: min=x, max=y, pct=NULL
            if min_rate == max_rate:
                warnings.append("range_equal_values")
            return min_rate, max_rate, None, json.dumps(warnings)
        else:
            warnings.append("range_parse_failed")
            return None, None, None, json.dumps(warnings)

    # Try to match single value
    single_match = re.search(r'^([\d.,]+)', rate_str)
    if single_match:
        rate = parse_single_rate(single_match.group(1))
        rate = validate_rate(rate)

        if rate is not None:
            # Single value: min=max=pct=value
            return rate, rate, rate, json.dumps(warnings)
        else:
            warnings.append("single_value_parse_failed")
            return None, None, None, json.dumps(warnings)

    # No match found
    warnings.append(f"unrecognized_format_{original_str[:20]}")
    return None, None, None, json.dumps(warnings)


def parse_single_rate(rate_str: str) -> Optional[float]:
    """
    Parse a single rate string to float.

    Handles both comma and decimal point separators.

    Args:
        rate_str: Rate string like "20,2" or "20.2"

    Returns:
        Float value or None if parsing fails
    """
    if not rate_str:
        return None

    # Replace comma with dot for decimal separator
    rate_str = rate_str.replace(',', '.')

    try:
        value = float(rate_str)
        return value
    except ValueError:
        logger.warning(f"Failed to parse rate: {rate_str}")
        return None


def validate_rate(rate: Optional[float]) -> Optional[float]:
    """
    Validate that rate is within acceptable range (0-30).

    Args:
        rate: Rate to validate

    Returns:
        Rate if valid, None otherwise
    """
    if rate is None:
        return None

    if not (0 <= rate <= 30):
        logger.warning(f"Rate {rate} is outside valid range (0-30), setting to None")
        return None

    return rate


def parse_term_label(term_str: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Parse term label to extract label and months.

    Examples:
    - "1 tháng" => ("1 tháng", 1)
    - "6 tháng" => ("6 tháng", 6)
    - "12 tháng" => ("12 tháng", 12)
    - "Không kỳ hạn" => ("Không kỳ hạn", 0)

    Args:
        term_str: Term label string

    Returns:
        Tuple of (label, months) or (None, None) if parsing fails
    """
    if not term_str:
        return None, None

    term_str = normalize_text(term_str)

    # Handle special cases
    if "không kỳ hạn" in term_str.lower():
        return "Không kỳ hạn", 0

    # Extract number and unit
    match = re.search(r'(\d+)\s*(tháng|tuần|ngày)', term_str, re.IGNORECASE)
    if match:
        number = int(match.group(1))
        unit = match.group(2).lower()

        # Convert to months
        if unit.startswith('tháng'):
            months = number
        elif unit.startswith('tuần'):
            months = number // 4  # Approximate
        elif unit.startswith('ngày'):
            months = 0  # Less than 1 month
        else:
            months = number

        return term_str, months

    return term_str, None


def extract_page_updated_text(html_content: str) -> Optional[str]:
    """
    Extract page update text from HTML content.

    Looks for patterns like:
    - "Bảng ... cập nhật ..."
    - Timestamps or titles like "[1/2026]"

    Args:
        html_content: HTML content to search

    Returns:
        Extracted update text or None
    """
    if not html_content:
        return None

    # Look for common patterns
    patterns = [
        r'Bảng[^.]*cập nhật[^.]*\.',
        r'\[\d{1,2}/\d{4}\]',  # [1/2026]
        r'Cập nhật[^.]*\.',
        r'ngày\s+\d{1,2}/\d{1,2}/\d{4}',  # ngày 3/1/2025
    ]

    for pattern in patterns:
        match = re.search(pattern, html_content, re.IGNORECASE)
        if match:
            return normalize_text(match.group(0))

    return None


def get_utc_timestamp() -> str:
    """
    Get current UTC timestamp in ISO8601 format.

    Returns:
        UTC timestamp string
    """
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
