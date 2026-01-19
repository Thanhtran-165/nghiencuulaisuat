"""
Tests for new datasets (auctions, secondary trading, policy rates)
"""
import pytest
from datetime import date

from app.db.schema import DatabaseManager
from tests.conftest import (
    sample_auction_data,
    sample_secondary_trading_data,
    sample_policy_rates_data
)


class TestAuctionData:
    """Test auction data insertion and retrieval"""

    def test_insert_auction_results(self, temp_db: DatabaseManager, sample_auction_data):
        """Test inserting auction results"""
        count = temp_db.insert_auction_results(sample_auction_data)
        assert count == len(sample_auction_data)

    def test_auction_idempotency(self, temp_db: DatabaseManager, sample_auction_data):
        """Test that inserting same auction data twice doesn't create duplicates"""
        # Insert first time
        count1 = temp_db.insert_auction_results(sample_auction_data)

        # Insert second time (should update, not insert new rows)
        count2 = temp_db.insert_auction_results(sample_auction_data)

        assert count1 == count2 == len(sample_auction_data)

        # Verify only 2 records exist
        result = temp_db.con.execute("SELECT COUNT(*) FROM gov_auction_results").fetchone()
        assert result[0] == len(sample_auction_data)


class TestSecondaryTradingData:
    """Test secondary trading data insertion and retrieval"""

    def test_insert_secondary_trading(self, temp_db: DatabaseManager, sample_secondary_trading_data):
        """Test inserting secondary trading data"""
        count = temp_db.insert_secondary_trading(sample_secondary_trading_data)
        assert count == len(sample_secondary_trading_data)

    def test_secondary_trading_idempotency(self, temp_db: DatabaseManager, sample_secondary_trading_data):
        """Test that inserting same secondary trading data twice doesn't create duplicates"""
        # Insert first time
        count1 = temp_db.insert_secondary_trading(sample_secondary_trading_data)

        # Insert second time (should update, not insert new rows)
        count2 = temp_db.insert_secondary_trading(sample_secondary_trading_data)

        assert count1 == count2 == len(sample_secondary_trading_data)

        # Verify only 2 records exist
        result = temp_db.con.execute("SELECT COUNT(*) FROM gov_secondary_trading").fetchone()
        assert result[0] == len(sample_secondary_trading_data)


class TestPolicyRatesData:
    """Test policy rates data insertion and retrieval"""

    def test_insert_policy_rates(self, temp_db: DatabaseManager, sample_policy_rates_data):
        """Test inserting policy rates"""
        count = temp_db.insert_policy_rates(sample_policy_rates_data)
        assert count == len(sample_policy_rates_data)

    def test_policy_rates_idempotency(self, temp_db: DatabaseManager, sample_policy_rates_data):
        """Test that inserting same policy rate data twice doesn't create duplicates"""
        # Insert first time
        count1 = temp_db.insert_policy_rates(sample_policy_rates_data)

        # Insert second time (should update, not insert new rows)
        count2 = temp_db.insert_policy_rates(sample_policy_rates_data)

        assert count1 == count2 == len(sample_policy_rates_data)

        # Verify only 3 records exist
        result = temp_db.con.execute("SELECT COUNT(*) FROM policy_rates").fetchone()
        assert result[0] == len(sample_policy_rates_data)


class TestCoverageEndpoint:
    """Test coverage endpoint includes all tables"""

    def test_coverage_all_tables(self, temp_db: DatabaseManager):
        """Test that coverage query works for all 6 tables"""
        tables = [
            'gov_yield_curve',
            'gov_yield_change_stats',
            'interbank_rates',
            'gov_auction_results',
            'gov_secondary_trading',
            'policy_rates'
        ]

        for table in tables:
            try:
                sql = f"""
                SELECT
                    MIN(date) as earliest_date,
                    MAX(date) as latest_date,
                    COUNT(DISTINCT date) as date_count
                FROM {table}
                """

                result = temp_db.con.execute(sql).fetchone()

                # Should return a result even if no data
                assert result is not None
                assert len(result) == 3

            except Exception as e:
                pytest.fail(f"Coverage query failed for table {table}: {e}")
