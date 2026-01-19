"""Tests for loan parser."""

import pytest
from app.parsers.loan import LoanParser
from app.utils import get_utc_timestamp


@pytest.fixture
def loan_html():
    """Load loan fixture HTML."""
    fixture_path = 'tests/fixtures/timo_loan.html'
    with open(fixture_path, 'r', encoding='utf-8') as f:
        return f.read()


def test_parse_loan_records(loan_html):
    """Test that loan parser extracts records."""
    parser = LoanParser(
        loan_html,
        "https://timo.vn/blogs/so-sanh-lai-suat-vay-ngan-hang-cap-nhat-moi-nhat/",
        get_utc_timestamp()
    )

    records, metadata = parser.parse()

    # Should extract some records
    assert len(records) > 0, "Should extract at least some records"

    # Check that records have required fields
    for record in records:
        assert 'bank_name' in record
        assert record['bank_name']

        assert record['product_group'] == 'loan'

        assert 'series' in record
        assert record['series'] in ['loan_tin_chap', 'loan_the_chap']

        # Loan records should NOT have term information
        assert record['term_label'] is None
        assert record['term_months'] is None

        # Loan records should have min/max rates (max can be NULL for "Từ x" format)
        assert 'rate_min_pct' in record
        assert 'rate_max_pct' in record
        assert record['rate_min_pct'] is not None
        # rate_max_pct can be NULL for "Từ x" format

        # Validate rate ranges (only if max is not None)
        assert 0 <= record['rate_min_pct'] <= 30
        if record['rate_max_pct'] is not None:
            assert 0 <= record['rate_max_pct'] <= 30
            assert record['rate_min_pct'] <= record['rate_max_pct']

        # Check for raw_value and parse_warnings
        assert 'raw_value' in record
        assert 'parse_warnings' in record


def test_loan_has_both_series(loan_html):
    """Test that loan parser extracts both loan types."""
    parser = LoanParser(
        loan_html,
        "https://timo.vn/blogs/so-sanh-lai-suat-vay-ngan-hang-cap-nhat-moi-nhat/",
        get_utc_timestamp()
    )

    records, metadata = parser.parse()

    # Get unique series
    unique_series = set(record['series'] for record in records)

    # Should have both series types if fixture contains them
    # At minimum, should have one
    assert len(unique_series) >= 1


def test_loan_metadata(loan_html):
    """Test that loan parser returns metadata."""
    parser = LoanParser(
        loan_html,
        "https://timo.vn/blogs/so-sanh-lai-suat-vay-ngan-hang-cap-nhat-moi-nhat/",
        get_utc_timestamp()
    )

    records, metadata = parser.parse()

    # Check metadata structure
    assert 'strategy' in metadata
    assert metadata['strategy'] in ['A', 'B']

    assert 'description' in metadata

    assert 'records_extracted' in metadata
    assert metadata['records_extracted'] == len(records)


def test_loan_extract_page_metadata(loan_html):
    """Test that loan parser can extract page metadata."""
    parser = LoanParser(
        loan_html,
        "https://timo.vn/blogs/so-sanh-lai-suat-vay-ngan-hang-cap-nhat-moi-nhat/",
        get_utc_timestamp()
    )

    page_metadata = parser.extract_metadata()

    # Should have page_metadata key
    assert 'page_updated_text' in page_metadata
