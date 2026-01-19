"""
Tests for Transmission Analytics module
"""
import pytest
from datetime import date, timedelta
from app.analytics.transmission import TransmissionAnalytics
from app.analytics.snapshot import DailySnapshotGenerator


class TestTransmissionMetrics:
    """Test transmission metrics computation"""

    def test_compute_daily_metrics_with_no_data(self, temp_db):
        """Test metrics computation when no data exists"""
        analytics = TransmissionAnalytics(temp_db)
        target_date = date(2024, 1, 15)

        metrics, alerts = analytics.compute_daily_metrics(target_date)

        # Should return empty metrics but not crash
        assert isinstance(metrics, dict)
        assert isinstance(alerts, list)

        # Score should be None when no data available
        assert metrics.get('transmission_score') is None
        assert metrics.get('regime_bucket') is None

    def test_compute_curve_metrics(self, temp_db, sample_yield_curve_data):
        """Test curve metrics computation"""
        # Insert sample data
        for record in sample_yield_curve_data:
            temp_db.insert_yield_curve([record])

        analytics = TransmissionAnalytics(temp_db)
        target_date = date(2024, 1, 15)

        metrics = analytics._compute_curve_metrics(target_date)

        # Check that metrics are computed
        assert 'level_10y' in metrics
        assert 'slope_10y_2y' in metrics
        assert 'slope_5y_2y' in metrics
        assert 'curvature' in metrics
        assert 'curve_data_available' in metrics

        # Check values are reasonable
        if metrics['level_10y'] is not None:
            assert isinstance(metrics['level_10y'], float)

        if metrics['slope_10y_2y'] is not None:
            assert isinstance(metrics['slope_10y_2y'], float)

    def test_compute_liquidity_metrics(self, temp_db, sample_interbank_data):
        """Test liquidity metrics computation"""
        # Insert sample data
        for record in sample_interbank_data:
            temp_db.insert_interbank_rates([record])

        analytics = TransmissionAnalytics(temp_db)
        target_date = date(2024, 1, 15)

        metrics = analytics._compute_liquidity_metrics(target_date)

        # Check that metrics are computed
        assert 'ib_on' in metrics
        assert 'ib_1w' in metrics
        assert 'ib_1m' in metrics
        assert 'ib_spread_1m_on' in metrics
        assert 'liquidity_data_available' in metrics

        # Check values
        if metrics['ib_on'] is not None:
            assert isinstance(metrics['ib_on'], float)
            assert metrics['ib_on'] == 0.5  # From sample data

    def test_compute_supply_metrics(self, temp_db, sample_auction_data):
        """Test supply metrics computation"""
        # Insert sample data
        for record in sample_auction_data:
            temp_db.insert_auction_results([record])

        analytics = TransmissionAnalytics(temp_db)
        target_date = date(2024, 1, 15)

        metrics = analytics._compute_supply_metrics(target_date)

        # Check that metrics are computed
        assert 'auction_sold_total_5d' in metrics
        assert 'auction_bid_to_cover_median_20d' in metrics
        assert 'auction_cutoff_yield_change_5d' in metrics
        assert 'supply_data_available' in metrics

        # Check values
        if metrics['auction_sold_total_5d'] is not None:
            assert isinstance(metrics['auction_sold_total_5d'], (int, float))

    def test_compute_demand_metrics(self, temp_db, sample_secondary_trading_data):
        """Test demand metrics computation"""
        # Insert sample data
        for record in sample_secondary_trading_data:
            temp_db.insert_secondary_trading([record])

        analytics = TransmissionAnalytics(temp_db)
        target_date = date(2024, 1, 15)

        metrics = analytics._compute_demand_metrics(target_date)

        # Check that metrics are computed
        assert 'secondary_value_total_5d' in metrics
        assert 'secondary_value_zscore_60d' in metrics
        assert 'demand_data_available' in metrics

        # Check values
        if metrics['secondary_value_total_5d'] is not None:
            assert isinstance(metrics['secondary_value_total_5d'], (int, float))

    def test_compute_policy_metrics(self, temp_db, sample_policy_rates_data):
        """Test policy metrics computation"""
        # Insert sample data
        for record in sample_policy_rates_data:
            temp_db.insert_policy_rates([record])

        analytics = TransmissionAnalytics(temp_db)
        target_date = date(2024, 1, 15)

        metrics = analytics._compute_policy_metrics(target_date)

        # Check that metrics are computed
        assert 'policy_rate_latest' in metrics
        assert 'policy_change_flag' in metrics
        assert 'policy_data_available' in metrics

        # Check values
        if metrics['policy_rate_latest'] is not None:
            assert isinstance(metrics['policy_rate_latest'], (int, float))


class TestRegimeBuckets:
    """Test regime bucket mapping"""

    def test_map_bucket_very_easy(self):
        """Test B0 bucket mapping (score <= 20)"""
        analytics = TransmissionAnalytics(None)

        assert analytics.map_bucket(0) == 'B0'
        assert analytics.map_bucket(10) == 'B0'
        assert analytics.map_bucket(20) == 'B0'

    def test_map_bucket_easy(self):
        """Test B1 bucket mapping (20-40)"""
        analytics = TransmissionAnalytics(None)

        assert analytics.map_bucket(21) == 'B1'
        assert analytics.map_bucket(30) == 'B1'
        assert analytics.map_bucket(40) == 'B1'

    def test_map_bucket_neutral(self):
        """Test B2 bucket mapping (40-60)"""
        analytics = TransmissionAnalytics(None)

        assert analytics.map_bucket(41) == 'B2'
        assert analytics.map_bucket(50) == 'B2'
        assert analytics.map_bucket(60) == 'B2'

    def test_map_bucket_tight(self):
        """Test B3 bucket mapping (60-80)"""
        analytics = TransmissionAnalytics(None)

        assert analytics.map_bucket(61) == 'B3'
        assert analytics.map_bucket(70) == 'B3'
        assert analytics.map_bucket(80) == 'B3'

    def test_map_bucket_very_tight(self):
        """Test B4 bucket mapping (>= 80)"""
        analytics = TransmissionAnalytics(None)

        assert analytics.map_bucket(81) == 'B4'
        assert analytics.map_bucket(90) == 'B4'
        assert analytics.map_bucket(100) == 'B4'


class TestAlertDetection:
    """Test alert detection"""

    def test_detect_alerts_no_data(self, temp_db):
        """Test alert detection with no data"""
        analytics = TransmissionAnalytics(temp_db)
        metrics = {}

        alerts = analytics.detect_alerts(metrics)

        assert isinstance(alerts, list)
        # Should return empty list when no metrics available
        assert len(alerts) == 0

    def test_detect_alerts_liquidity_spike(self, temp_db, sample_interbank_data):
        """Test liquidity spike alert detection"""
        analytics = TransmissionAnalytics(temp_db)

        # Create metrics with high interbank rate
        metrics = {
            'ib_on': 2.5,  # Very high
            'liquidity_data_available': True
        }

        alerts = analytics.detect_alerts(metrics)

        # Should have liquidity spike alert
        liquidity_alerts = [a for a in alerts if a['alert_type'] == 'ALERT_LIQUIDITY_SPIKE']
        assert len(liquidity_alerts) > 0
        assert liquidity_alerts[0]['severity'] == 'HIGH'

    def test_detect_alerts_auction_weak(self, temp_db, sample_auction_data):
        """Test weak auction alert detection"""
        analytics = TransmissionAnalytics(temp_db)

        # Create metrics with low bid-to-cover
        metrics = {
            'auction_bid_to_cover_median_20d': 1.0,  # Very low
            'supply_data_available': True
        }

        alerts = analytics.detect_alerts(metrics)

        # Should have auction weak alert
        auction_alerts = [a for a in alerts if a['alert_type'] == 'ALERT_AUCTION_WEAK']
        assert len(auction_alerts) > 0

    def test_detect_alerts_turnover_drop(self, temp_db, sample_secondary_trading_data):
        """Test turnover drop alert detection"""
        analytics = TransmissionAnalytics(temp_db)

        # Create metrics with negative z-score (low turnover)
        metrics = {
            'secondary_value_zscore_60d': -2.5,  # Very low
            'demand_data_available': True
        }

        alerts = analytics.detect_alerts(metrics)

        # Should have turnover drop alert
        turnover_alerts = [a for a in alerts if a['alert_type'] == 'ALERT_TURNOVER_DROP']
        assert len(turnover_alerts) > 0


class TestTopDrivers:
    """Test top drivers computation"""

    def test_get_top_drivers_empty(self, temp_db):
        """Test getting top drivers with no metrics"""
        analytics = TransmissionAnalytics(temp_db)
        metrics = {}

        drivers = analytics.get_top_drivers(metrics, n=3)

        assert isinstance(drivers, list)
        assert len(drivers) == 0

    def test_get_top_drivers_with_metrics(self, temp_db):
        """Test getting top drivers with sample metrics"""
        analytics = TransmissionAnalytics(temp_db)

        # Create metrics with various z-scores
        metrics = {
            'ib_on_zscore': 2.5,
            'slope_10y_2y_zscore': -1.8,
            'auction_sold_total_5d_zscore': 1.2,
            'secondary_value_total_5d_zscore': -2.0,
            'policy_rate_change_zscore': 0.5
        }

        drivers = analytics.get_top_drivers(metrics, n=3)

        assert isinstance(drivers, list)
        assert len(drivers) == 3

        # Check that drivers are sorted by absolute contribution
        contributions = [d['contribution'] for d in drivers]
        assert contributions == sorted(contributions, key=abs, reverse=True)

        # Check that each driver has name and contribution
        for driver in drivers:
            assert 'name' in driver
            assert 'contribution' in driver


class TestSnapshotGenerator:
    """Test daily snapshot generation"""

    def test_generate_snapshot_no_data(self, temp_db):
        """Test snapshot generation with no data"""
        generator = DailySnapshotGenerator(temp_db)
        target_date = date(2024, 1, 15)

        snapshot = generator.generate_snapshot(target_date)

        # Should return a valid snapshot structure
        assert 'date' in snapshot
        assert 'tom_tat' in snapshot
        assert 'so_voi_hom_qua' in snapshot
        assert 'dien_giai' in snapshot
        assert 'watchlist' in snapshot
        assert 'ghi_chu' in snapshot

        # Check data availability warning
        assert len(snapshot['ghi_chu']) > 0
        assert any('⚠️' in note for note in snapshot['ghi_chu'])

    def test_generate_snapshot_with_data(
        self,
        temp_db,
        sample_yield_curve_data,
        sample_interbank_data,
        sample_auction_data,
        sample_secondary_trading_data,
        sample_policy_rates_data
    ):
        """Test snapshot generation with sample data"""
        # Insert sample data
        for record in sample_yield_curve_data:
            temp_db.insert_yield_curve([record])

        for record in sample_interbank_data:
            temp_db.insert_interbank_rates([record])

        for record in sample_auction_data:
            temp_db.insert_auction_results([record])

        for record in sample_secondary_trading_data:
            temp_db.insert_secondary_trading([record])

        for record in sample_policy_rates_data:
            temp_db.insert_policy_rates([record])

        # Compute transmission metrics first
        analytics = TransmissionAnalytics(temp_db)
        target_date = date(2024, 1, 15)
        metrics, alerts = analytics.compute_daily_metrics(target_date)
        temp_db.insert_transmission_metrics(target_date.strftime('%Y-%m-%d'), metrics)

        if alerts:
            temp_db.insert_transmission_alerts(target_date.strftime('%Y-%m-%d'), alerts)

        # Generate snapshot
        generator = DailySnapshotGenerator(temp_db)
        snapshot = generator.generate_snapshot(target_date)

        # Check structure
        assert snapshot['date'] == '2024-01-15'
        assert 'tom_tat' in snapshot
        assert 'so_voi_hom_qua' in snapshot
        assert 'dien_giai' in snapshot
        assert 'watchlist' in snapshot
        assert 'ghi_chu' in snapshot

        # Check tom_tat
        if metrics.get('transmission_score'):
            assert snapshot['tom_tat']['diem_so'] == metrics['transmission_score']
            assert snapshot['tom_tat']['nhom'] == metrics['regime_bucket']

        # Check dien_giai
        assert isinstance(snapshot['dien_giai'], list)

        # Check ghi_chu
        assert isinstance(snapshot['ghi_chu'], list)


class TestTransmissionScore:
    """Test transmission score computation"""

    def test_compute_transmission_score_no_data(self, temp_db):
        """Test score computation with no data"""
        analytics = TransmissionAnalytics(temp_db)
        target_date = date(2024, 1, 15)

        # Empty metrics
        metrics = {}

        score, components = analytics._compute_transmission_score(target_date, metrics)

        # Score should be None when no data available
        assert score is None
        assert isinstance(components, dict)

    def test_compute_transmission_score_with_partial_data(self, temp_db):
        """Test score computation with partial data"""
        analytics = TransmissionAnalytics(temp_db)
        target_date = date(2024, 1, 15)

        # Partial metrics (only some data available)
        metrics = {
            'level_10y_zscore': 0.5,
            'ib_on_zscore': None,  # Missing
            'auction_sold_total_5d_zscore': 1.0,
            'secondary_value_total_5d_zscore': -0.5,
            'policy_rate_change_zscore': 0.0
        }

        score, components = analytics._compute_transmission_score(target_date, metrics)

        # Score should be computed from available data
        if score is not None:
            assert isinstance(score, float)
            assert 0 <= score <= 100

        # Check components
        assert isinstance(components, dict)
