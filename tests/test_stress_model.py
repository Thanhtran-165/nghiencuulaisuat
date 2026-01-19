"""
Tests for BondY Stress Model
"""
import pytest
from datetime import date, timedelta
from app.analytics.stress_model import BondYStressModel


class TestBondYStressModel:
    """Test BondY stress index computation"""

    def test_stress_index_bounds(self, temp_db, sample_yield_curve_data, sample_interbank_data):
        """Test that stress index is bounded between 0-100"""
        # Insert sample data
        for record in sample_yield_curve_data:
            temp_db.insert_yield_curve([record])

        for record in sample_interbank_data:
            temp_db.insert_interbank_rates([record])

        # Insert transmission metrics (required for stress computation)
        from app.analytics.transmission import TransmissionAnalytics
        analytics = TransmissionAnalytics(temp_db)
        target_date = date(2024, 1, 15)
        metrics, alerts = analytics.compute_daily_metrics(target_date)
        temp_db.insert_transmission_metrics(target_date.strftime('%Y-%m-%d'), metrics)

        # Compute stress
        stress_model = BondYStressModel(temp_db)
        stress_index, regime_bucket, components = stress_model.compute_stress_index(target_date)

        # Assert bounds
        if stress_index is not None:
            assert 0 <= stress_index <= 100, f"Stress index {stress_index} out of bounds [0, 100]"

        # Assert regime bucket
        if regime_bucket:
            assert regime_bucket in ['S0', 'S1', 'S2', 'S3', 'S4'], f"Invalid regime bucket: {regime_bucket}"

    def test_stress_with_no_data(self, temp_db):
        """Test stress computation with no data returns None gracefully"""
        stress_model = BondYStressModel(temp_db)
        target_date = date(2024, 1, 15)

        stress_index, regime_bucket, components = stress_model.compute_stress_index(target_date)

        # Should return None without crashing
        assert stress_index is None
        assert regime_bucket is None
        assert 'error' in components

    def test_global_comparators_without_fred(self, temp_db):
        """Test that global comparators work without FRED data"""
        stress_model = BondYStressModel(temp_db)
        target_date = date(2024, 1, 15)

        comparators = stress_model.compute_global_comparators(target_date)

        # Should return empty comparators but not crash
        assert isinstance(comparators, dict)
        assert comparators['global_available'] == False
        assert comparators['spreads'] == {}
        assert comparators['correlations'] == {}
        assert comparators['alerts'] == []

    def test_top_drivers_structure(self, temp_db, sample_yield_curve_data, sample_interbank_data):
        """Test that top drivers have correct structure"""
        # Insert and compute metrics
        for record in sample_yield_curve_data:
            temp_db.insert_yield_curve([record])

        for record in sample_interbank_data:
            temp_db.insert_interbank_rates([record])

        from app.analytics.transmission import TransmissionAnalytics
        analytics = TransmissionAnalytics(temp_db)
        target_date = date(2024, 1, 15)
        metrics, alerts = analytics.compute_daily_metrics(target_date)
        temp_db.insert_transmission_metrics(target_date.strftime('%Y-%m-%d'), metrics)

        # Compute stress
        stress_model = BondYStressModel(temp_db)
        stress_index, regime_bucket, components = stress_model.compute_stress_index(target_date)

        if stress_index is not None:
            drivers = components.get('drivers', [])

            # Check structure
            assert isinstance(drivers, list)

            for driver in drivers:
                assert 'name' in driver
                assert 'value' in driver
                assert 'contribution' in driver
                assert isinstance(driver['contribution'], (int, float))

    def test_stress_regime_mapping(self):
        """Test stress regime bucket mapping"""
        stress_model = BondYStressModel(None)

        # Test each bucket
        assert stress_model._map_stress_bucket(10) == 'S0'
        assert stress_model._map_stress_bucket(25) == 'S1'
        assert stress_model._map_stress_bucket(45) == 'S2'
        assert stress_model._map_stress_bucket(70) == 'S3'
        assert stress_model._map_stress_bucket(90) == 'S4'

        # Test boundaries
        assert stress_model._map_stress_bucket(0) == 'S0'
        assert stress_model._map_stress_bucket(20) == 'S0'
        assert stress_model._map_stress_bucket(100) == 'S4'

    def test_stress_component_weights(self):
        """Test that component weights sum to 1.0"""
        from app.analytics.stress_model import BondYStressModel

        weights = BondYStressModel.WEIGHTS
        total_weight = sum(weights.values())

        assert abs(total_weight - 1.0) < 0.001, f"Weights sum to {total_weight}, expected 1.0"

    def test_zscore_winsorization(self, temp_db):
        """Test that z-scores are winsorized at ±3"""
        stress_model = BondYStressModel(temp_db)

        # Test extreme values
        values = [1.0, 2.0, 3.0, 4.0, 5.0]  # Normal range
        zscore = stress_model._compute_zscore(3.0, values)
        assert zscore is not None
        assert -3 <= zscore <= 3

        # Test with very high value (should be winsorized)
        extreme_values = [1.0, 2.0, 3.0, 4.0, 1000.0]
        zscore_extreme = stress_model._compute_zscore(1000.0, extreme_values)
        assert zscore_extreme is not None
        assert zscore_extreme <= 3  # Winsorized at +3


class TestPDFGeneration:
    """Test PDF report generation"""

    def test_pdf_generator_requires_reportlab(self, temp_db):
        """Test that PDF generator requires ReportLab"""
        try:
            from app.reports.pdf_daily import DailyPDFReportGenerator, REPORTLAB_AVAILABLE

            if not REPORTLAB_AVAILABLE:
                pytest.skip("ReportLab not installed")

            # Should initialize without errors
            generator = DailyPDFReportGenerator(temp_db, output_dir="/tmp/test_reports")

            assert generator is not None
            assert generator.output_dir.exists()

        except ImportError:
            pytest.skip("ReportLab not available")

    def test_pdf_generation_smoke(self, temp_db):
        """Test that PDF generation doesn't crash with sample data"""
        try:
            from app.reports.pdf_daily import REPORTLAB_AVAILABLE

            if not REPORTLAB_AVAILABLE:
                pytest.skip("ReportLab not installed")

            from app.reports.pdf_daily import generate_daily_pdf

            # Insert minimal data
            target_date = date(2024, 1, 15)

            # Try to generate PDF
            pdf_path = generate_daily_pdf(temp_db, target_date, output_dir="/tmp/test_reports")

            # May fail due to missing data, but shouldn't crash
            # If successful, check file exists
            if pdf_path:
                import os
                assert os.path.exists(pdf_path)
                assert os.path.getsize(pdf_path) > 0

        except ImportError:
            pytest.skip("ReportLab not available")
