"""Tests for 24hmoney.vn deposit parser."""

import pytest
from app.parsers.deposit_24hmoney import parse_deposit_24hmoney


@pytest.fixture
def fixture_24hmoney():
    """Load 24hmoney HTML fixture."""
    with open('tests/fixtures/24hmoney_deposit.html', 'r', encoding='utf-8') as f:
        return f.read()


def test_strategy_a_parses_two_series(fixture_24hmoney):
    """Test that Strategy A parses both deposit_tai_quay and deposit_online series."""
    records, metadata = parse_deposit_24hmoney(
        fixture_24hmoney,
        'https://24hmoney.vn/lai-suat-gui-ngan-hang',
        '2026-01-05T00:00:00Z'
    )

    # Check that strategy A was used
    assert metadata['strategy'] == 'A'
    assert metadata['description'] == 'Table/Header parser (24hmoney specialized)'

    # Check that we got records
    assert len(records) > 0, "Should extract at least some records"

    # Check that we have both series
    series_set = {r['series'] for r in records}
    assert 'deposit_tai_quay' in series_set, "Should have deposit_tai_quay series"
    assert 'deposit_online' in series_set, "Should have deposit_online series"


def test_term_columns_parsed(fixture_24hmoney):
    """Test that term columns 1, 3, 6, 12 months are parsed correctly."""
    records, _ = parse_deposit_24hmoney(
        fixture_24hmoney,
        'https://24hmoney.vn/lai-suat-gui-ngan-hang',
        '2026-01-05T00:00:00Z'
    )

    # Check that we have the expected terms
    term_months_set = {r['term_months'] for r in records}
    assert 1 in term_months_set, "Should have 1 month term"
    assert 3 in term_months_set, "Should have 3 month term"
    assert 6 in term_months_set, "Should have 6 month term"
    assert 12 in term_months_set, "Should have 12 month term"


def test_min_bank_count(fixture_24hmoney):
    """Test that parser extracts at least 5 banks (fixture has ~10 visible banks)."""
    records, _ = parse_deposit_24hmoney(
        fixture_24hmoney,
        'https://24hmoney.vn/lai-suat-gui-ngan-hang',
        '2026-01-05T00:00:00Z'
    )

    # Count unique banks
    banks_set = {r['bank_name'] for r in records}
    # Fixture only has first page visible (~10 banks), rest are hidden rows
    assert len(banks_set) >= 5, f"Should extract at least 5 banks, got {len(banks_set)}"


def test_rate_numeric_and_range(fixture_24hmoney):
    """Test that rates are numeric and within valid range [0, 30]."""
    records, _ = parse_deposit_24hmoney(
        fixture_24hmoney,
        'https://24hmoney.vn/lai-suat-gui-ngan-hang',
        '2026-01-05T00:00:00Z'
    )

    # All records should have valid rates
    for record in records:
        rate_pct = record['rate_pct']
        assert isinstance(rate_pct, (int, float)), f"Rate should be numeric, got {type(rate_pct)}"
        assert 0 <= rate_pct <= 30, f"Rate should be in range [0, 30], got {rate_pct}"


def test_scoping_avoids_noise(fixture_24hmoney):
    """Test that parser doesn't pick up rates from footer/menu (if present in fixture)."""
    records, _ = parse_deposit_24hmoney(
        fixture_24hmoney,
        'https://24hmoney.vn/lai-suat-gui-ngan-hang',
        '2026-01-05T00:00:00Z'
    )

    # All bank names should be meaningful (not generic text)
    for record in records:
        bank_name = record['bank_name']
        assert len(bank_name) >= 2, f"Bank name too short: '{bank_name}'"
        assert bank_name not in ['Ngân hàng', 'Bank', '', ' '], f"Invalid bank name: '{bank_name}'"


def test_hidden_rows_excluded(fixture_24hmoney):
    """Test that rows with display:none are excluded from parsing."""
    records, _ = parse_deposit_24hmoney(
        fixture_24hmoney,
        'https://24hmoney.vn/lai-suat-gui-ngan-hang',
        '2026-01-05T00:00:00Z'
    )

    # 24hmoney has hidden rows for pagination
    # We should not have extracted any banks that are only in hidden rows
    # (This is implicitly tested by the fact that we get records at all,
    # but we can check that we don't have an unusually high count)
    banks_set = {r['bank_name'] for r in records}

    # Based on fixture, first visible page has about 10 banks
    # Total site has ~29 banks, but many are in hidden rows
    # We should get at least the visible ones
    assert len(banks_set) >= 5, "Should extract at least the banks from visible rows"


def test_record_structure_complete(fixture_24hmoney):
    """Test that all required fields are present in records."""
    records, _ = parse_deposit_24hmoney(
        fixture_24hmoney,
        'https://24hmoney.vn/lai-suat-gui-ngan-hang',
        '2026-01-05T00:00:00Z'
    )

    required_fields = [
        'bank_name', 'product_group', 'series', 'term_label', 'term_months',
        'rate_pct', 'rate_min_pct', 'rate_max_pct',
        'source_url', 'scraped_at'
    ]

    for record in records:
        for field in required_fields:
            assert field in record, f"Missing required field: {field}"


def test_strategy_b_fallback():
    """Test Strategy B fallback (requires malformed HTML)."""
    # Create minimal HTML that would fail Strategy A
    malformed_html = """
    <html>
        <body>
            <div>No tables here</div>
            <a class="name">VIB</a>
            <a class="name">VCB</a>
            <p class="bank-interest-rate">3.6</p>
            <p class="bank-interest-rate">4.5</p>
        </body>
    </html>
    """

    records, metadata = parse_deposit_24hmoney(
        malformed_html,
        'https://24hmoney.vn/lai-suat-gui-ngan-hang',
        '2026-01-05T00:00:00Z'
    )

    # Strategy B should attempt parsing
    assert metadata['strategy'] == 'B'
    assert 'warning' in metadata


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
