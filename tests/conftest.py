"""
Test configuration and fixtures
"""
import sys
import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import date

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.schema import DatabaseManager


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test.duckdb"

    db = DatabaseManager(str(db_path))
    db.connect()
    db.initialize_schema()

    yield db

    db.close()
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_yield_curve_data():
    """Sample yield curve data for testing"""
    return [
        {
            'date': '2024-01-15',
            'tenor_label': '2Y',
            'tenor_days': 730,
            'spot_rate_continuous': 5.25,
            'par_yield': 5.30,
            'spot_rate_annual': 5.28,
            'source': 'TEST',
            'fetched_at': '2024-01-15T10:00:00'
        },
        {
            'date': '2024-01-15',
            'tenor_label': '5Y',
            'tenor_days': 1825,
            'spot_rate_continuous': 6.10,
            'par_yield': 6.15,
            'spot_rate_annual': 6.12,
            'source': 'TEST',
            'fetched_at': '2024-01-15T10:00:00'
        },
        {
            'date': '2024-01-15',
            'tenor_label': '10Y',
            'tenor_days': 3650,
            'spot_rate_continuous': 7.05,
            'par_yield': 7.10,
            'spot_rate_annual': 7.08,
            'source': 'TEST',
            'fetched_at': '2024-01-15T10:00:00'
        }
    ]


@pytest.fixture
def sample_interbank_data():
    """Sample interbank rate data for testing"""
    return [
        {
            'date': '2024-01-15',
            'tenor_label': 'ON',
            'rate': 0.5,
            'source': 'TEST',
            'fetched_at': '2024-01-15T10:00:00'
        },
        {
            'date': '2024-01-15',
            'tenor_label': '1W',
            'rate': 0.65,
            'source': 'TEST',
            'fetched_at': '2024-01-15T10:00:00'
        },
        {
            'date': '2024-01-15',
            'tenor_label': '1M',
            'rate': 0.85,
            'source': 'TEST',
            'fetched_at': '2024-01-15T10:00:00'
        }
    ]


@pytest.fixture
def sample_auction_data():
    """Sample auction data for testing"""
    return [
        {
            'date': '2024-01-15',
            'instrument_type': 'Government Bond',
            'tenor_label': '5Y',
            'tenor_days': 1825,
            'amount_offered': 5000.0,
            'amount_sold': 4500.0,
            'bid_to_cover': 1.2,
            'cut_off_yield': 6.125,
            'avg_yield': 6.118,
            'source': 'HNX_AUCTION',
            'raw_file': 'test_auction_001',
            'fetched_at': '2024-01-15T10:00:00'
        },
        {
            'date': '2024-01-15',
            'instrument_type': 'T-Bill',
            'tenor_label': '3M',
            'tenor_days': 90,
            'amount_offered': 3000.0,
            'amount_sold': 3000.0,
            'bid_to_cover': 1.5,
            'cut_off_yield': 0.85,
            'avg_yield': 0.84,
            'source': 'HNX_AUCTION',
            'raw_file': 'test_auction_002',
            'fetched_at': '2024-01-15T10:00:00'
        }
    ]


@pytest.fixture
def sample_secondary_trading_data():
    """Sample secondary trading data for testing"""
    return [
        {
            'date': '2024-01-15',
            'segment': 'Government Bond',
            'bucket_label': 'Credit Institution',
            'volume': 15000.0,
            'value': 16500.0,
            'avg_yield': 6.25,
            'source': 'HNX_TRADING',
            'raw_file': 'test_trading_001',
            'fetched_at': '2024-01-15T10:00:00'
        },
        {
            'date': '2024-01-15',
            'segment': 'Government Bond',
            'bucket_label': 'Individual',
            'volume': 500.0,
            'value': 550.0,
            'avg_yield': 6.30,
            'source': 'HNX_TRADING',
            'raw_file': 'test_trading_002',
            'fetched_at': '2024-01-15T10:00:00'
        }
    ]


@pytest.fixture
def sample_policy_rates_data():
    """Sample policy rates data for testing"""
    return [
        {
            'date': '2024-01-15',
            'rate_name': 'Refinancing Rate',
            'rate': 4.5,
            'source': 'SBV_POLICY',
            'raw_file': 'test_policy_001',
            'fetched_at': '2024-01-15T10:00:00'
        },
        {
            'date': '2024-01-15',
            'rate_name': 'Rediscount Rate',
            'rate': 3.0,
            'source': 'SBV_POLICY',
            'raw_file': 'test_policy_002',
            'fetched_at': '2024-01-15T10:00:00'
        },
        {
            'date': '2024-01-15',
            'rate_name': 'Base Rate',
            'rate': 4.0,
            'source': 'SBV_POLICY',
            'raw_file': 'test_policy_003',
            'fetched_at': '2024-01-15T10:00:00'
        }
    ]
