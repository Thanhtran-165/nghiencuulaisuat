"""Tests for utility functions."""

import json
import pytest
from app.utils import parse_rate_range


def test_parse_rate_range_from_prefix():
    """Test 'Từ x' format => min=x, max=NULL, pct=NULL with warning."""
    min_rate, max_rate, pct, warnings_json = parse_rate_range("Từ 6,9")

    assert min_rate == 6.9
    assert max_rate is None
    assert pct is None

    warnings = json.loads(warnings_json)
    assert "from_prefix_no_max" in warnings


def test_parse_rate_range_dash():
    """Test '6.9-12.0' format => min=6.9, max=12.0, pct=NULL."""
    min_rate, max_rate, pct, warnings_json = parse_rate_range("6.9-12.0")

    assert min_rate == 6.9
    assert max_rate == 12.0
    assert pct is None

    warnings = json.loads(warnings_json)
    assert len(warnings) == 0  # No warnings for valid range


def test_parse_rate_range_en_dash():
    """Test '6.9–12.0' format with en dash => min=6.9, max=12.0, pct=NULL."""
    min_rate, max_rate, pct, warnings_json = parse_rate_range("6.9–12.0")

    assert min_rate == 6.9
    assert max_rate == 12.0
    assert pct is None

    warnings = json.loads(warnings_json)
    assert len(warnings) == 0


def test_parse_rate_range_single_value():
    """Test '20' format => min=max=pct=20."""
    min_rate, max_rate, pct, warnings_json = parse_rate_range("20")

    assert min_rate == 20.0
    assert max_rate == 20.0
    assert pct == 20.0

    warnings = json.loads(warnings_json)
    assert len(warnings) == 0


def test_parse_rate_range_comma_decimal():
    """Test '20,5' format with comma decimal => min=max=pct=20.5."""
    min_rate, max_rate, pct, warnings_json = parse_rate_range("20,5")

    assert min_rate == 20.5
    assert max_rate == 20.5
    assert pct == 20.5

    warnings = json.loads(warnings_json)
    assert len(warnings) == 0


def test_parse_rate_range_empty_string():
    """Test empty string => all NULL with warning."""
    min_rate, max_rate, pct, warnings_json = parse_rate_range("")

    assert min_rate is None
    assert max_rate is None
    assert pct is None

    warnings = json.loads(warnings_json)
    assert "empty_value" in warnings


def test_parse_rate_range_dash_only():
    """Test '—' dash only => all NULL with warning."""
    min_rate, max_rate, pct, warnings_json = parse_rate_range("—")

    assert min_rate is None
    assert max_rate is None
    assert pct is None

    warnings = json.loads(warnings_json)
    assert any("invalid_value" in w for w in warnings)


def test_parse_rate_range_na():
    """Test 'N/A' => all NULL with warning."""
    min_rate, max_rate, pct, warnings_json = parse_rate_range("N/A")

    assert min_rate is None
    assert max_rate is None
    assert pct is None

    warnings = json.loads(warnings_json)
    assert any("invalid_value" in w for w in warnings)


def test_parse_rate_range_out_of_bounds():
    """Test value out of range (0-30) => all NULL with warning."""
    min_rate, max_rate, pct, warnings_json = parse_rate_range("50")

    assert min_rate is None
    assert max_rate is None
    assert pct is None

    warnings = json.loads(warnings_json)
    assert "single_value_parse_failed" in warnings


def test_parse_rate_range_negative():
    """Test negative value => all NULL with warning."""
    min_rate, max_rate, pct, warnings_json = parse_rate_range("-5")

    # -5 doesn't match numeric pattern (starts with dash is treated as separator)
    assert min_rate is None
    assert max_rate is None
    assert pct is None

    warnings = json.loads(warnings_json)
    # Negative numbers don't match pattern, so they get unrecognized_format warning
    assert len(warnings) > 0


def test_parse_rate_range_whitespace():
    """Test value with whitespace => correctly parsed."""
    min_rate, max_rate, pct, warnings_json = parse_rate_range("  6.9  ")

    assert min_rate == 6.9
    assert max_rate == 6.9
    assert pct == 6.9

    warnings = json.loads(warnings_json)
    assert len(warnings) == 0


def test_parse_rate_range_from_with_space():
    """Test 'Từ 6.9' with space => min=6.9, max=NULL."""
    min_rate, max_rate, pct, warnings_json = parse_rate_range("Từ 6.9")

    assert min_rate == 6.9
    assert max_rate is None
    assert pct is None

    warnings = json.loads(warnings_json)
    assert "from_prefix_no_max" in warnings


def test_parse_rate_range_from_lowercase():
    """Test 'từ 6.9' lowercase => min=6.9, max=NULL."""
    min_rate, max_rate, pct, warnings_json = parse_rate_range("từ 6.9")

    assert min_rate == 6.9
    assert max_rate is None
    assert pct is None

    warnings = json.loads(warnings_json)
    assert "from_prefix_no_max" in warnings


def test_parse_rate_warnings_is_valid_json():
    """Test that warnings_json is always valid JSON."""
    test_cases = [
        "Từ 6,9",
        "6.9-12.0",
        "20",
        "",
        "—",
        "N/A",
        "50",  # Out of range
    ]

    for test_input in test_cases:
        min_rate, max_rate, pct, warnings_json = parse_rate_range(test_input)

        # Should be able to parse as JSON without error
        warnings = json.loads(warnings_json)
        assert isinstance(warnings, list)
