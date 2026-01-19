"""
Tests for data providers
"""
import pytest
from app.providers.base import BaseProvider


def test_parse_vietnamese_float():
    """Test parsing Vietnamese float format"""
    provider = BaseProvider()

    # Test comma as decimal separator
    assert provider._parse_vietnamese_float("5,25") == 5.25
    assert provider._parse_vietnamese_float("6,50") == 6.50

    # Test dot as decimal separator
    assert provider._parse_vietnamese_float("5.25") == 5.25

    # Test empty/invalid values
    assert provider._parse_vietnamese_float("") is None
    assert provider._parse_vietnamese_float("-") is None
    assert provider._parse_vietnamese_float("N/A") is None

    # Test with spaces
    assert provider._parse_vietnamese_float(" 5,25 ") == 5.25


def test_parse_vietnamese_int():
    """Test parsing Vietnamese integer format"""
    provider = BaseProvider()

    assert provider._parse_vietnamese_int("5") == 5
    assert provider._parse_vietnamese_int("5,0") == 5
    assert provider._parse_vietnamese_int("") is None


def test_standardize_date():
    """Test date parsing with multiple formats"""
    provider = BaseProvider()

    formats = ['%d/%m/%Y', '%Y-%m-%d']

    # Test DD/MM/YYYY
    result = provider._standardize_date("15/01/2024", formats)
    assert result.day == 15
    assert result.month == 1
    assert result.year == 2024

    # Test YYYY-MM-DD
    result = provider._standardize_date("2024-01-15", formats)
    assert result.day == 15
    assert result.month == 1
    assert result.year == 2024

    # Test invalid format
    result = provider._standardize_date("invalid", formats)
    assert result is None


def test_hnx_tenor_matching():
    """Test HNX yield curve provider tenor matching"""
    from app.providers.hnx_yield_curve import HNXYieldCurveProvider

    provider = HNXYieldCurveProvider()

    # Test Vietnamese tenors
    assert provider._match_tenor("3 tháng") == ('3M', 90)
    assert provider._match_tenor("1 năm") == ('1Y', 365)
    assert provider._match_tenor("10 năm") == ('10Y', 3650)

    # Test English tenors
    assert provider._match_tenor("2Y") == ('2Y', 730)
    assert provider._match_tenor("5Y") == ('5Y', 1825)


def test_sbv_tenor_matching():
    """Test SBV interbank provider tenor matching"""
    from app.providers.sbv_interbank import SBVInterbankProvider

    provider = SBVInterbankProvider()

    # Test Vietnamese tenors
    assert provider._match_tenor("qua đêm") == ('ON', 0)
    assert provider._match_tenor("1 tuần") == ('1W', 7)
    assert provider._match_tenor("3 tháng") == ('3M', 90)

    # Test English tenors
    assert provider._match_tenor("ON") == ('ON', 0)
    assert provider._match_tenor("1W") == ('1W', 7)


def test_abo_tenor_matching():
    """Test ABO provider tenor matching"""
    from app.providers.abo_market_watch import ABOMarketWatchProvider

    provider = ABOMarketWatchProvider()

    # Test government bond tenors
    assert provider._match_abo_tenor("2Y") == ('2Y', 730)
    assert provider._match_abo_tenor("5 YEAR") == ('5Y', 1825)
    assert provider._match_abo_tenor("10-YEAR") == ('10Y', 3650)

    # Test interbank tenors
    assert provider._match_abo_interbank_tenor("ON") == ('ON', 0)
    assert provider._match_abo_interbank_tenor("1M") == ('1M', 30)
    assert provider._match_abo_interbank_tenor("3 MONTH") == ('3M', 90)


def test_raw_data_storage_disabled(monkeypatch, tmp_path):
    """Test that raw data storage can be disabled"""
    from app.config import settings
    from app.providers.base import BaseProvider

    # Disable raw storage
    monkeypatch.setattr(settings, 'enable_raw_storage', False)

    provider = BaseProvider()

    # Should return None when storage is disabled
    result = provider._save_raw("test.txt", b"test content")
    assert result is None
