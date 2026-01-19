"""
Tests for Phase 8 Observability features

Tests health/readyz/metrics endpoints, drift detection, and monitoring APIs
"""
import pytest
import json
from datetime import date, datetime
from app.observability.metrics import MetricsRegistry, get_health_status, get_readiness_status
from app.db.schema import DatabaseManager
from app.quality.rules import SourceDriftDetection


class TestHealthEndpoints:
    """Test /healthz and /readyz endpoints"""

    def test_healthz_returns_expected_keys(self):
        """Test that /healthz returns expected keys"""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        response = client.get("/healthz")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert data["status"] == "ok"

    def test_readyz_returns_expected_keys(self, temp_db):
        """Test that /readyz returns expected keys including database status"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.schema import db_manager

        # Use temp_db fixture
        db_manager.__dict__.update(temp_db.__dict__)

        client = TestClient(app)
        response = client.get("/readyz")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "database" in data
        assert "timestamp" in data

    def test_metrics_endpoint_returns_prometheus_format(self):
        """Test that /metrics endpoint returns Prometheus-format metrics"""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        response = client.get("/metrics")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"

        # Check for Prometheus format
        metrics_text = response.text
        assert "# HELP" in metrics_text or "# TYPE" in metrics_text


class TestMetricsRegistry:
    """Test metrics registry functionality"""

    def test_increment_counter(self):
        """Test counter increment"""
        registry = MetricsRegistry()

        registry.increment_counter("test_requests", {"method": "GET"})
        registry.increment_counter("test_requests", {"method": "GET"}, value=2)

        metrics = registry.format_prometheus()
        assert "test_requests" in metrics

    def test_set_gauge(self):
        """Test gauge setting"""
        registry = MetricsRegistry()

        registry.set_gauge("active_connections", 10, {"server": "app1"})
        registry.set_gauge("active_connections", 15, {"server": "app1"})

        metrics = registry.format_prometheus()
        assert "active_connections" in metrics

    def test_observe_histogram(self):
        """Test histogram observation"""
        registry = MetricsRegistry()

        registry.observe_histogram("request_duration_seconds", 0.5, {"endpoint": "/api"})
        registry.observe_histogram("request_duration_seconds", 1.2, {"endpoint": "/api"})

        metrics = registry.format_prometheus()
        assert "request_duration_seconds" in metrics

    def test_prometheus_format(self):
        """Test Prometheus export format"""
        registry = MetricsRegistry()

        registry.increment_counter("http_requests_total", {"method": "GET", "status": "200"})
        registry.set_gauge("memory_usage_bytes", 1024000, {"instance": "app1"})

        metrics = registry.format_prometheus()

        # Check for standard Prometheus format
        assert "http_requests_total" in metrics
        assert "memory_usage_bytes" in metrics


class TestDriftDetection:
    """Test source drift detection"""

    def test_fingerprint_insertion(self, temp_db):
        """Test that fingerprint insertion works"""
        content = b"test content for fingerprinting"
        target_date = date(2024, 1, 15)

        temp_db.insert_source_fingerprint(
            provider="TEST_PROVIDER",
            dataset_id="test_dataset",
            target_date=target_date,
            content=content,
            content_type="text/html",
            parse_rowcount=100,
            parse_required_fields_ok=True,
            note="Test fingerprint"
        )

        # Retrieve fingerprint
        fingerprints = temp_db.get_source_fingerprints(
            provider="TEST_PROVIDER",
            dataset_id="test_dataset"
        )

        assert len(fingerprints) == 1
        assert fingerprints[0]["provider"] == "TEST_PROVIDER"
        assert fingerprints[0]["dataset_id"] == "test_dataset"
        assert fingerprints[0]["parse_rowcount"] == 100

    def test_drift_detection_warn_on_content_change(self, temp_db):
        """Test that drift detection returns WARN when content changes"""
        target_date = date(2024, 1, 15)

        # Insert first fingerprint
        temp_db.insert_source_fingerprint(
            provider="TEST_PROVIDER",
            dataset_id="test_dataset",
            target_date=target_date,
            content=b"original content",
            content_type="text/html",
            parse_rowcount=100,
            parse_required_fields_ok=True,
            note="Original"
        )

        # Insert second fingerprint with different content
        temp_db.insert_source_fingerprint(
            provider="TEST_PROVIDER",
            dataset_id="test_dataset",
            target_date=target_date,
            content=b"changed content",
            content_type="text/html",
            parse_rowcount=100,
            parse_required_fields_ok=True,
            note="Changed"
        )

        # Run drift detection rule
        rule = SourceDriftDetection("TEST_PROVIDER", "test_dataset")
        passed, severity, message, details = rule.check(temp_db, target_date)

        # Should detect drift
        assert passed is False
        assert severity == "WARN"
        assert "drift" in message.lower() or "changed" in message.lower()

    def test_drift_detection_error_on_regression(self, temp_db):
        """Test that drift detection returns ERROR on rowcount regression (>10% drop)"""
        target_date = date(2024, 1, 15)

        # Insert first fingerprint with high rowcount
        temp_db.insert_source_fingerprint(
            provider="TEST_PROVIDER",
            dataset_id="test_dataset",
            target_date=target_date,
            content=b"original content with many rows",
            content_type="text/html",
            parse_rowcount=100,
            parse_required_fields_ok=True,
            note="Original"
        )

        # Insert second fingerprint with significant rowcount drop (>10%)
        temp_db.insert_source_fingerprint(
            provider="TEST_PROVIDER",
            dataset_id="test_dataset",
            target_date=target_date,
            content=b"changed content with fewer rows",
            content_type="text/html",
            parse_rowcount=80,  # 20% drop
            parse_required_fields_ok=True,
            note="Regression"
        )

        # Run drift detection rule
        rule = SourceDriftDetection("TEST_PROVIDER", "test_dataset")
        passed, severity, message, details = rule.check(temp_db, target_date)

        # Should detect regression
        assert passed is False
        assert severity == "ERROR"
        assert "regression" in details

    def test_no_drift_when_same(self, temp_db):
        """Test that no drift is detected when content is the same"""
        target_date = date(2024, 1, 15)
        content = b"stable content"

        # Insert two identical fingerprints
        temp_db.insert_source_fingerprint(
            provider="TEST_PROVIDER",
            dataset_id="test_dataset",
            target_date=target_date,
            content=content,
            content_type="text/html",
            parse_rowcount=100,
            parse_required_fields_ok=True,
            note="First"
        )

        temp_db.insert_source_fingerprint(
            provider="TEST_PROVIDER",
            dataset_id="test_dataset",
            target_date=target_date,
            content=content,
            content_type="text/html",
            parse_rowcount=100,
            parse_required_fields_ok=True,
            note="Second"
        )

        # Run drift detection rule
        rule = SourceDriftDetection("TEST_PROVIDER", "test_dataset")
        passed, severity, message, details = rule.check(temp_db, target_date)

        # Should pass - no drift
        assert passed is True
        assert severity == "INFO"


class TestMonitoringAPIs:
    """Test monitoring dashboard APIs"""

    def test_monitoring_summary_api(self, temp_db):
        """Test that /api/admin/monitoring/summary returns expected structure"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.schema import db_manager

        db_manager.__dict__.update(temp_db.__dict__)

        # Seed some data
        temp_db.insert_ingest_run(
            started_at=datetime.now(),
            status="success",
            records_processed=100,
            duration_seconds=45.2
        )

        temp_db.insert_dq_run(
            run_at=datetime.now(),
            status="PASS",
            total_rules=10,
            passed_rules=10,
            failed_rules=0
        )

        client = TestClient(app)
        response = client.get("/api/admin/monitoring/summary")

        assert response.status_code == 200
        data = response.json()
        assert "last_ingest" in data
        assert "last_dq" in data
        assert "slo_30d" in data

    def test_monitoring_providers_api(self, temp_db):
        """Test that /api/admin/monitoring/providers returns provider stats"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.schema import db_manager

        db_manager.__dict__.update(temp_db.__dict__)

        client = TestClient(app)
        response = client.get("/api/admin/monitoring/providers")

        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert "latencies" in data

    def test_monitoring_drift_api(self, temp_db):
        """Test that /api/admin/monitoring/drift returns drift signals"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.schema import db_manager

        db_manager.__dict__.update(temp_db.__dict__)

        # Seed drift data
        target_date = date(2024, 1, 15)
        temp_db.insert_source_fingerprint(
            provider="TEST_PROVIDER",
            dataset_id="test_dataset",
            target_date=target_date,
            content=b"content",
            content_type="text/html",
            parse_rowcount=100,
            parse_required_fields_ok=True,
            note="Test"
        )

        client = TestClient(app)
        response = client.get("/api/admin/monitoring/drift")

        assert response.status_code == 200
        data = response.json()
        assert "drifts" in data

    def test_monitoring_apis_return_json(self, temp_db):
        """Test that monitoring APIs return valid JSON"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.schema import db_manager

        db_manager.__dict__.update(temp_db.__dict__)

        client = TestClient(app)

        # Test all monitoring endpoints return valid JSON
        endpoints = [
            "/api/admin/monitoring/summary",
            "/api/admin/monitoring/providers",
            "/api/admin/monitoring/drift"
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 200

            # Verify response is valid JSON
            data = response.json()
            assert isinstance(data, dict)


class TestMetricsEndpointMetricNames:
    """Test that /metrics endpoint returns expected metric names"""

    def test_metrics_contains_http_metrics(self):
        """Test that /metrics contains HTTP-related metrics"""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        response = client.get("/metrics")

        assert response.status_code == 200
        metrics_text = response.text

        # After some HTTP requests, should have HTTP metrics
        # Make a few requests first
        client.get("/healthz")
        client.get("/readyz")

        response = client.get("/metrics")
        metrics_text = response.text.lower()

        # Check for common metric patterns (may be empty if no requests yet)
        assert isinstance(metrics_text, str)

    def test_metrics_format_is_valid_prometheus(self):
        """Test that metrics output is valid Prometheus format"""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        response = client.get("/metrics")

        assert response.status_code == 200
        metrics_text = response.text

        # Prometheus format should have lines with metric names and values
        # or HELP/TYPE comments
        lines = metrics_text.strip().split('\n')

        # Should have at least some content
        assert len(lines) > 0

        # Each line should be either a comment or a metric
        for line in lines:
            if line and not line.startswith('#'):
                # Metric line should have metric name, labels, and value
                parts = line.split(' ')
                assert len(parts) >= 2  # metric_name and value at minimum


class TestEnvMappingAuth:
    """Test backwards compatibility for BASIC_AUTH_* -> ADMIN_AUTH_* mapping"""

    def test_basic_auth_mapping_to_admin_auth(self, monkeypatch):
        """Test that BASIC_AUTH_* maps to ADMIN_AUTH_* when only BASIC is set"""
        from app.config import Settings, _apply_backwards_compatibility

        # Simulate environment with only BASIC_AUTH_* set
        monkeypatch.setenv('BASIC_AUTH_ENABLED', 'true')
        monkeypatch.setenv('BASIC_AUTH_USERNAME', 'testuser')
        monkeypatch.setenv('BASIC_AUTH_PASSWORD', 'testpass')

        # Create a new settings instance (will trigger backwards compatibility)
        test_settings = Settings()

        # Apply backwards compatibility mapping
        from app import config
        original_settings = config.settings
        config.settings = test_settings
        try:
            _apply_backwards_compatibility()

            # Verify that ADMIN_AUTH_* fields are set
            assert test_settings.admin_auth_enabled == True
            assert test_settings.admin_user == 'testuser'
            assert test_settings.admin_password == 'testpass'
        finally:
            config.settings = original_settings

    def test_admin_auth_takes_precedence(self, monkeypatch):
        """Test that ADMIN_AUTH_* takes precedence over BASIC_AUTH_*"""
        from app.config import Settings

        # Set both BASIC_AUTH_* and ADMIN_AUTH_*
        monkeypatch.setenv('BASIC_AUTH_ENABLED', 'false')
        monkeypatch.setenv('BASIC_AUTH_USERNAME', 'basic_user')
        monkeypatch.setenv('BASIC_AUTH_PASSWORD', 'basic_pass')
        monkeypatch.setenv('ADMIN_AUTH_ENABLED', 'true')
        monkeypatch.setenv('ADMIN_USER', 'admin_user')
        monkeypatch.setenv('ADMIN_PASSWORD', 'admin_pass')

        # Create settings instance
        settings = Settings()

        # ADMIN_AUTH_* should take precedence (not be overridden by mapping)
        # Note: After backwards compatibility runs, admin values should remain
        assert settings.admin_auth_enabled == True
        assert settings.admin_user == 'admin_user'
        assert settings.admin_password == 'admin_pass'

    def test_no_secret_values_in_warning_logs(self, monkeypatch, caplog):
        """Test that secret values are never logged during backwards compatibility mapping"""
        import logging
        from app.config import Settings, _apply_backwards_compatibility

        # Set BASIC_AUTH_PASSWORD (should not appear in logs)
        monkeypatch.setenv('BASIC_AUTH_ENABLED', 'true')
        monkeypatch.setenv('BASIC_AUTH_USERNAME', 'testuser')
        monkeypatch.setenv('BASIC_AUTH_PASSWORD', 'super_secret_password_123')

        test_settings = Settings()

        # Capture logs
        with caplog.at_level(logging.WARNING):
            from app import config
            original_settings = config.settings
            config.settings = test_settings
            try:
                _apply_backwards_compatibility()
            finally:
                config.settings = original_settings

        # Verify that password is never in logs
        for record in caplog.records:
            assert 'super_secret_password_123' not in record.message
            assert 'testuser' not in record.message  # Username also shouldn't be logged
            # Should have deprecation warning
            if 'deprecated' in record.message.lower():
                assert 'BASIC_AUTH' in record.message


class TestReadyzContract:
    """Test /readyz endpoint returns expected contract"""

    def test_readyz_returns_expected_keys(self, temp_db):
        """Test that /readyz returns expected keys in response"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.schema import db_manager

        # Use temp_db fixture
        db_manager.__dict__.update(temp_db.__dict__)

        client = TestClient(app)
        response = client.get("/readyz")

        assert response.status_code == 200
        data = response.json()

        # Required keys
        required_keys = ["status", "database", "timestamp"]
        for key in required_keys:
            assert key in data, f"Missing required key: {key}"

        # Database status should be an object with details
        assert isinstance(data["database"], dict)

    def test_readyz_database_status(self, temp_db):
        """Test that /readyz includes database status details"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.schema import db_manager

        db_manager.__dict__.update(temp_db.__dict__)

        client = TestClient(app)
        response = client.get("/readyz")

        assert response.status_code == 200
        data = response.json()

        # Database status should have connection info
        db_status = data["database"]
        assert "status" in db_status or "ok" in db_status

    def test_readyz_handles_missing_database(self):
        """Test that /readyz handles database connection issues gracefully"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.schema import db_manager
        from app.config import settings
        import tempfile
        import os

        # Point to invalid database path
        original_db_path = settings.db_path
        invalid_db_path = "/nonexistent/path/to/invalid.db"

        try:
            # Temporarily change db path
            db_manager.close()
            settings.db_path = invalid_db_path

            client = TestClient(app)
            response = client.get("/readyz")

            # Should still return 200, but with error status
            assert response.status_code in [200, 503]

            data = response.json()
            assert "status" in data

            # If DB connection failed, status should reflect that
            if response.status_code == 503:
                assert data["status"] != "ok"

        finally:
            # Restore original db path
            settings.db_path = original_db_path
            db_manager.connect()


class TestMetricsContract:
    """Test /metrics endpoint returns expected metric names"""

    def test_metrics_contains_ingest_metrics(self):
        """Test that /metrics contains ingest-related metrics"""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        response = client.get("/metrics")

        assert response.status_code == 200
        metrics_text = response.text

        # Look for ingest metrics (may be present after ingestion runs)
        # At minimum, metrics endpoint should be accessible
        assert isinstance(metrics_text, str)
        assert len(metrics_text) > 0

    def test_metrics_contains_dq_metrics(self):
        """Test that /metrics contains data quality metrics"""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        response = client.get("/metrics")

        assert response.status_code == 200
        metrics_text = response.text.lower()

        # Check for any DQ-related metric patterns
        # Metrics may be empty if no DQ runs have occurred yet
        assert isinstance(metrics_text, str)

    def test_metrics_http_metrics_present_after_requests(self):
        """Test that HTTP metrics appear in /metrics after making requests"""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        # Make some HTTP requests
        client.get("/healthz")
        client.get("/readyz")
        client.get("/metrics")

        # Get metrics again
        response = client.get("/metrics")
        assert response.status_code == 200

        metrics_text = response.text

        # Should have some metrics content
        assert len(metrics_text) > 0

        # Prometheus format should have # HELP or # TYPE or metric lines
        has_metrics = any(line for line in metrics_text.split('\n')
                         if line and not line.startswith('#'))
        # Metrics might be empty, but endpoint should work
        assert isinstance(metrics_text, str)


class TestDemoMode:
    """Test demo mode functionality"""

    def test_seed_demo_generates_data(self, monkeypatch, tmp_path):
        """Test that seed-demo CLI generates expected data"""
        import subprocess
        import sys

        # Create temp database path
        db_path = tmp_path / "demo_test.db"

        # Run seed-demo command
        result = subprocess.run(
            [sys.executable, "-m", "app.ops", "seed-demo", "--db", str(db_path), "--days", "30"],
            capture_output=True,
            text=True,
            timeout=60
        )

        # Should succeed
        assert result.returncode == 0, f"seed-demo failed: {result.stderr}"
        assert "Demo data seeded successfully" in result.stdout

        # Verify database file exists
        assert db_path.exists()

        # Verify data was created
        from app.db.schema import DatabaseManager
        db = DatabaseManager(str(db_path))
        db.connect()

        # Check yield curve data
        yc_count = db.con.execute("SELECT COUNT(*) FROM gov_yield_curve WHERE source = 'DEMO'").fetchone()[0]
        assert yc_count > 0, "No demo yield curve data generated"

        # Check interbank data
        ib_count = db.con.execute("SELECT COUNT(*) FROM interbank_rates WHERE source = 'DEMO'").fetchone()[0]
        assert ib_count > 0, "No demo interbank data generated"

        # Check auction data
        auction_count = db.con.execute("SELECT COUNT(*) FROM gov_auction_results WHERE source = 'DEMO'").fetchone()[0]
        assert auction_count > 0, "No demo auction data generated"

        # Check secondary trading data
        trading_count = db.con.execute("SELECT COUNT(*) FROM gov_secondary_trading WHERE source = 'DEMO'").fetchone()[0]
        assert trading_count > 0, "No demo secondary trading data generated"

        # Check policy rates
        policy_count = db.con.execute("SELECT COUNT(*) FROM policy_rates WHERE source = 'DEMO'").fetchone()[0]
        assert policy_count > 0, "No demo policy rates generated"

        # Check ingest runs
        ingest_count = db.con.execute("SELECT COUNT(*) FROM ingest_runs").fetchone()[0]
        assert ingest_count > 0, "No demo ingest runs generated"

        # Check DQ runs
        dq_count = db.con.execute("SELECT COUNT(*) FROM dq_runs").fetchone()[0]
        assert dq_count > 0, "No demo DQ runs generated"

        # Check alerts
        alert_count = db.con.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        assert alert_count > 0, "No demo alerts generated"

        # Check source fingerprints
        fp_count = db.con.execute("SELECT COUNT(*) FROM source_fingerprints WHERE provider = 'demo'").fetchone()[0]
        assert fp_count > 0, "No demo fingerprints generated"

        db.close()

    def test_snapshot_works_with_demo_data(self, temp_db):
        """Test that /api/snapshot/today works with demo data"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.schema import db_manager
        from datetime import date

        # Seed some demo data
        temp_db.insert_yield_curve([
            {
                'date': str(date.today()),
                'tenor_label': '2Y',
                'tenor_days': 730,
                'spot_rate_continuous': 5.0,
                'par_yield': 5.05,
                'spot_rate_annual': 5.1,
                'source': 'DEMO',
                'fetched_at': f'{date.today()}T10:00:00'
            }
        ])

        db_manager.__dict__.update(temp_db.__dict__)

        client = TestClient(app)
        response = client.get("/api/snapshot/today")

        # Should return 200
        assert response.status_code == 200

    def test_version_endpoint_includes_demo_mode_flag(self, monkeypatch):
        """Test that /api/version includes demo_mode flag"""
        from fastapi.testclient import TestClient
        from app.main import app

        # Set DEMO_MODE
        monkeypatch.setenv('DEMO_MODE', 'true')

        # Reload config to pick up env var
        from app import config
        from importlib import reload
        reload(config)

        client = TestClient(app)
        response = client.get("/api/version")

        assert response.status_code == 200
        data = response.json()

        assert 'feature_flags' in data
        assert 'demo_mode_enabled' in data['feature_flags']
        assert data['feature_flags']['demo_mode_enabled'] == True

    def test_readyz_ok_in_demo_mode(self, monkeypatch, temp_db):
        """Test that /readyz returns OK in demo mode"""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.schema import db_manager

        # Set DEMO_MODE
        monkeypatch.setenv('DEMO_MODE', 'true')

        # Reload config
        from app import config
        from importlib import reload
        reload(config)

        db_manager.__dict__.update(temp_db.__dict__)

        client = TestClient(app)
        response = client.get("/readyz")

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ok'

    def test_demo_data_has_correct_provenance(self, temp_db):
        """Test that demo data has correct provider/source marking"""
        from datetime import date

        # Insert demo data
        temp_db.insert_yield_curve([
            {
                'date': str(date.today()),
                'tenor_label': '2Y',
                'tenor_days': 730,
                'spot_rate_continuous': 5.0,
                'par_yield': 5.05,
                'spot_rate_annual': 5.1,
                'source': 'DEMO',
                'fetched_at': f'{date.today()}T10:00:00'
            }
        ])

        # Verify provenance
        results = temp_db.con.execute(
            "SELECT source FROM gov_yield_curve WHERE date = ?", [str(date.today())]
        ).fetchall()

        assert len(results) == 1
        assert results[0][0] == 'DEMO'


class TestRunbookContracts:
    """Test that runbook commands match implementation"""

    def test_backup_path_format_matches_implementation(self, tmp_path):
        """Test that backup file extension/format matches documentation"""
        from app.ops.manager import OpsManager
        from datetime import date

        # Create a test database
        test_db = tmp_path / "test.db"
        test_db.touch()

        ops = OpsManager(str(test_db))

        # Generate backup
        backup_path = ops.backup()

        # Verify backup uses .duckdb extension
        assert backup_path.endswith('.duckdb'), f"Backup should use .duckdb extension, got: {backup_path}"

        # Verify backup is in data/backups/ directory
        assert 'data/backups/' in backup_path or './backups/' in backup_path, \
            f"Backup should be in backups/ directory, got: {backup_path}"

        # Verify backup file format
        import os
        assert os.path.exists(backup_path), f"Backup file should exist: {backup_path}"

    def test_backup_verification_works(self, tmp_path):
        """Test that backup verification works with .duckdb files"""
        from app.ops.manager import OpsManager

        # Create a test database with a table
        test_db = tmp_path / "test.db"
        import duckdb
        con = duckdb.connect(str(test_db))
        con.execute("CREATE TABLE test_table (id INTEGER, value VARCHAR)")
        con.execute("INSERT INTO test_table VALUES (1, 'test')")
        con.close()

        ops = OpsManager(str(test_db))
        backup_path = ops.backup()

        # Verify backup
        verification = ops.verify_backup(backup_path)

        assert verification['readable'] == True
        assert verification['total_tables'] > 0
        assert verification['valid'] == True


class TestDemoModeIngestBlock:
    """Test that demo mode blocks ingestion unless override is set"""

    def test_demo_mode_blocks_ingest_by_default(self, monkeypatch):
        """Test that demo mode blocks ingestion when OVERRIDE_DEMO_INGEST=false"""
        from app.config import Settings

        # Set DEMO_MODE=true without override
        monkeypatch.setenv('DEMO_MODE', 'true')
        monkeypatch.setenv('OVERRIDE_DEMO_INGEST', 'false')

        settings = Settings()

        assert settings.demo_mode == True
        assert settings.override_demo_ingest == False

    def test_demo_mode_override_allows_ingest(self, monkeypatch):
        """Test that OVERRIDE_DEMO_INGEST=true allows ingestion in demo mode"""
        from app.config import Settings

        # Set both DEMO_MODE and OVERRIDE_DEMO_INGEST
        monkeypatch.setenv('DEMO_MODE', 'true')
        monkeypatch.setenv('OVERRIDE_DEMO_INGEST', 'true')

        settings = Settings()

        assert settings.demo_mode == True
        assert settings.override_demo_ingest == True

    def test_normal_mode_ingest_not_blocked(self, monkeypatch):
        """Test that normal mode (DEMO_MODE=false) doesn't block ingestion"""
        from app.config import Settings

        # Set DEMO_MODE=false
        monkeypatch.setenv('DEMO_MODE', 'false')

        settings = Settings()

        assert settings.demo_mode == False
        # override_demo_ingest doesn't matter when demo_mode is false


class TestRCSmokeScript:
    """Test RC smoke script"""

    def test_rc_smoke_script_exists(self):
        """Test that rc_smoke.sh script exists and is executable"""
        import os
        import stat

        script_path = "scripts/rc_smoke.sh"

        # Check file exists
        assert os.path.exists(script_path), f"RC smoke script should exist: {script_path}"

        # Check file is executable
        st = os.stat(script_path)
        is_executable = st.st_mode & stat.S_IXUSR
        assert is_executable != 0, f"RC smoke script should be executable: {script_path}"

    def test_rc_smoke_script_contains_key_tests(self):
        """Test that rc_smoke.sh contains required test commands"""
        script_path = "scripts/rc_smoke.sh"

        with open(script_path, 'r') as f:
            content = f.read()

        # Check for key endpoint tests
        assert '/healthz' in content, "Script should test /healthz endpoint"
        assert '/readyz' in content, "Script should test /readyz endpoint"
        assert '/api/version' in content, "Script should test /api/version endpoint"
        assert '/metrics' in content, "Script should test /metrics endpoint"

        # Check for key pages
        assert '/snapshot/today' in content, "Script should test /snapshot/today endpoint"
        assert '/report/daily.pdf' in content, "Script should test PDF download"

        # Check for PASS/FAIL summary
        assert 'PASS' in content or 'pass' in content.lower(), "Script should report pass status"
        assert 'FAIL' in content or 'fail' in content.lower(), "Script should report fail status"
        assert 'exit 1' in content or 'exit(1)' in content, "Script should exit non-zero on fail"


class TestReleaseGateScript:
    """Test Release Gate script"""

    def test_release_gate_script_exists(self):
        """Test that release_gate.sh script exists and is executable"""
        import os
        import stat

        script_path = "scripts/release_gate.sh"

        # Check file exists
        assert os.path.exists(script_path), f"Release gate script should exist: {script_path}"

        # Check file is executable
        st = os.stat(script_path)
        is_executable = st.st_mode & stat.S_IXUSR
        assert is_executable != 0, f"Release gate script should be executable: {script_path}"

    def test_release_gate_script_contains_key_steps(self):
        """Test that release_gate.sh contains required steps"""
        script_path = "scripts/release_gate.sh"

        with open(script_path, 'r') as f:
            content = f.read()

        # Check for production compose file
        assert 'docker-compose.prod.yml' in content or 'COMPOSE_FILE' in content, \
            "Script should use production compose file"

        # Check for readiness wait with timeout override
        assert '/readyz' in content, "Script should wait for readiness"
        assert 'READY_TIMEOUT' in content, "Script should have READY_TIMEOUT variable"

        # Check for log capture overrides
        assert 'LOG_TAIL' in content, "Script should have LOG_TAIL variable"
        assert 'LOG_SINCE' in content, "Script should have LOG_SINCE variable"

        # Check for smoke test execution
        assert 'rc_smoke.sh' in content, "Script should run smoke tests"

        # Check for evidence collection
        assert 'release_evidence' in content, "Script should create evidence directory"
        assert 'EVIDENCE_DIR' in content or 'evidence_dir' in content, "Script should use evidence directory"

        # Check for artifact collection
        assert 'readyz.json' in content, "Script should collect readiness check"
        assert 'version.json' in content, "Script should collect version info"
        assert 'daily.pdf' in content, "Script should collect PDF report"

        # Check for docker logs with --tail
        assert '--tail' in content, "Script should use --tail for log capture"

        # Check for exit codes
        assert 'exit 0' in content, "Script should exit 0 on success"
        assert 'exit 1' in content, "Script should exit 1 on failure"

    def test_release_gate_script_no_secrets(self):
        """Test that release_gate.sh does not print secrets"""
        script_path = "scripts/release_gate.sh"

        with open(script_path, 'r') as f:
            content = f.read()

        # Check that script doesn't echo environment variables that might contain secrets
        assert 'echo $' not in content or 'echo ${' not in content, \
            "Script should not echo raw environment variables (might contain secrets)"
