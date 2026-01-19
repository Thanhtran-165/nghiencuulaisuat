"""
Source Registry for Interest Rate Scrapers

Central configuration of all data sources for deposit and loan interest rates.
Each source has a unique source_id, URL, parser configuration, and metadata.
"""

from typing import Literal, List, Dict, Any
from dataclasses import dataclass

@dataclass
class SourceConfig:
    """Configuration for a single data source"""
    source_id: str  # Unique slug (e.g., "timo_deposit", "vcb_loan")
    url: str  # Full URL to scrape
    kind: Literal["deposit", "loan"]  # Source type
    expected_bank_list_mode: Literal["by_name", "by_table"]  # How to identify banks
    parser_module: str  # Python module path (e.g., "app.parsers.deposit_timo")
    notes: str  # Additional constraints or notes

    def __post_init__(self):
        """Validate source configuration"""
        if not self.source_id.isidentifier():
            raise ValueError(f"source_id must be a valid Python identifier: {self.source_id}")
        if not self.url.startswith("http"):
            raise ValueError(f"url must start with http/https: {self.url}")


# Source Registry
# All available data sources for scraping
SOURCES: List[SourceConfig] = [
    # ===== DEPOSIT SOURCES =====

    # Timo.vn - Deposit rates (existing)
    SourceConfig(
        source_id="timo_deposit",
        url="https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/",
        kind="deposit",
        expected_bank_list_mode="by_table",
        parser_module="app.parsers.deposit",
        notes="Original source. Has comprehensive deposit rates with multiple terms."
    ),

    # 24hmoney.vn - Deposit rates (static HTML tables)
    SourceConfig(
        source_id="24hmoney_deposit",
        url="https://24hmoney.vn/lai-suat-gui-ngan-hang",
        kind="deposit",
        expected_bank_list_mode="by_table",
        parser_module="app.parsers.deposit_24hmoney",
        notes="Static HTML tables with 29+ banks. Has separate tables for 'tại quầy' (offline) and 'trực tuyến' (online)."
    ),

    # ===== LOAN SOURCES =====

    # Timo.vn - Loan rates (existing)
    SourceConfig(
        source_id="timo_loan",
        url="https://timo.vn/blogs/lai-suat-vay-tin-chap-ngan-hang-nao-cao-nhat/",
        kind="loan",
        expected_bank_list_mode="by_table",
        parser_module="app.parsers.loan",
        notes="Original source. Covers unsecured loans with rate ranges."
    ),

    # TODO: Add 2+ new loan sources
    # Example candidates (to be researched):
    # - https://webvaynhanh.vn/bang-lai-suat-vay-tin-chap/
    # - Bank official loan pages
]


def get_source(source_id: str) -> SourceConfig:
    """
    Get source configuration by source_id.

    Args:
        source_id: Unique source identifier

    Returns:
        SourceConfig object

    Raises:
        KeyError: if source_id not found
    """
    for source in SOURCES:
        if source.source_id == source_id:
            return source
    raise KeyError(f"Source not found: {source_id}. Available sources: {[s.source_id for s in SOURCES]}")


def get_sources_by_kind(kind: Literal["deposit", "loan"]) -> List[SourceConfig]:
    """
    Get all sources of a specific kind.

    Args:
        kind: "deposit" or "loan"

    Returns:
        List of SourceConfig objects
    """
    return [s for s in SOURCES if s.kind == kind]


def get_all_source_ids() -> List[str]:
    """Get list of all source IDs"""
    return [s.source_id for s in SOURCES]


def get_source_urls() -> Dict[str, str]:
    """
    Get mapping of source_id to URL.

    Returns:
        Dict with source_id as key and URL as value
    """
    return {s.source_id: s.url for s in SOURCES}


# Parser module registry
# Maps source_id to parser function
PARSER_REGISTRY: Dict[str, Any] = {}


def register_parser(source_id: str):
    """
    Decorator to register a parser function for a source.

    Usage:
        @register_parser("timo_deposit")
        def parse_timo_deposit(html: str):
            ...
    """
    def decorator(func):
        PARSER_REGISTRY[source_id] = func
        return func
    return decorator
