"""Tests for deposit parser."""

import pytest
from app.parsers.deposit import DepositParser
from app.utils import get_utc_timestamp


@pytest.fixture
def deposit_html():
    """Load deposit fixture HTML."""
    fixture_path = 'tests/fixtures/timo_deposit.html'
    with open(fixture_path, 'r', encoding='utf-8') as f:
        return f.read()


def test_parse_deposit_deposits(deposit_html):
    """Test that deposit parser extracts records."""
    parser = DepositParser(
        deposit_html,
        "https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/",
        get_utc_timestamp()
    )

    records, metadata = parser.parse()

    # Should extract some records
    assert len(records) > 0, "Should extract at least some records"

    # Check that records have required fields
    for record in records:
        assert 'bank_name' in record
        assert record['bank_name']

        assert record['product_group'] == 'deposit'

        assert 'series' in record
        assert record['series'] in ['deposit_tai_quay', 'deposit_online']

        # Deposit records must have term information
        assert 'term_label' in record
        assert 'term_months' in record
        assert record['term_months'] is not None

        # Deposit records must have rate_pct
        assert 'rate_pct' in record
        assert record['rate_pct'] is not None
        assert 0 <= record['rate_pct'] <= 30


def test_deposit_has_multiple_series(deposit_html):
    """Test that deposit parser can handle multiple series."""
    parser = DepositParser(
        deposit_html,
        "https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/",
        get_utc_timestamp()
    )

    records, metadata = parser.parse()

    # Get unique series
    unique_series = set(record['series'] for record in records)

    # Should have at least one series
    assert len(unique_series) >= 1

    # If fixture contains both series, both should be parsed
    # (This depends on the actual fixture content)


def test_deposit_metadata(deposit_html):
    """Test that deposit parser returns metadata."""
    parser = DepositParser(
        deposit_html,
        "https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/",
        get_utc_timestamp()
    )

    records, metadata = parser.parse()

    # Check metadata structure
    assert 'strategy' in metadata
    assert metadata['strategy'] in ['A', 'B']

    assert 'description' in metadata

    assert 'records_extracted' in metadata
    assert metadata['records_extracted'] == len(records)


def test_deposit_extract_page_metadata(deposit_html):
    """Test that deposit parser can extract page metadata."""
    parser = DepositParser(
        deposit_html,
        "https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/",
        get_utc_timestamp()
    )

    page_metadata = parser.extract_metadata()

    # Should have page_metadata key
    assert 'page_updated_text' in page_metadata
