"""
API smoke tests for new endpoints
"""
import pytest
from fastapi.testclient import TestClient

from app import main as app_main
from datetime import date, datetime


@pytest.fixture
def client(temp_db, sample_auction_data, sample_secondary_trading_data, sample_policy_rates_data):
    """Create test client with seeded database"""
    today = date.today().isoformat()
    now = datetime.now().isoformat()

    # Seed database with sample data
    temp_db.insert_auction_results(sample_auction_data)
    temp_db.insert_secondary_trading(sample_secondary_trading_data)
    temp_db.insert_policy_rates(sample_policy_rates_data)
    temp_db.insert_yield_curve(
        [
            {
                "date": today,
                "tenor_label": "2Y",
                "tenor_days": 730,
                "spot_rate_continuous": 5.0,
                "par_yield": 5.1,
                "spot_rate_annual": 5.05,
                "source": "HNX_YC",
                "fetched_at": now,
            },
            {
                "date": today,
                "tenor_label": "5Y",
                "tenor_days": 1825,
                "spot_rate_continuous": 6.0,
                "par_yield": 6.1,
                "spot_rate_annual": 6.05,
                "source": "HNX_YC",
                "fetched_at": now,
            },
            {
                "date": today,
                "tenor_label": "10Y",
                "tenor_days": 3650,
                "spot_rate_continuous": 7.0,
                "par_yield": 7.1,
                "spot_rate_annual": 7.05,
                "source": "HNX_YC",
                "fetched_at": now,
            },
        ]
    )
    temp_db.insert_interbank_rates(
        [
            {
                "date": today,
                "tenor_label": "ON",
                "rate": 0.5,
                "source": "SBV",
                "fetched_at": now,
            },
            {
                "date": today,
                "tenor_label": "1W",
                "rate": 0.65,
                "source": "SBV",
                "fetched_at": now,
            },
        ]
    )

    # Override the global db_manager
    original_app_db = app_main.db_manager

    # Use our test database
    from app.api import routes as api_routes

    original_routes_db = api_routes.db_manager

    app_main.db_manager = temp_db
    api_routes.db_manager = temp_db

    yield TestClient(app_main.app)

    # Restore original
    app_main.db_manager = original_app_db
    api_routes.db_manager = original_routes_db


class TestAuctionAPI:
    """Test auction API endpoints"""

    def test_auctions_latest(self, client: TestClient):
        """Test GET /api/auctions/latest"""
        response = client.get("/api/auctions/latest")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        # Verify structure
        record = data[0]
        assert 'date' in record
        assert 'instrument_type' in record
        assert 'tenor_label' in record

    def test_auctions_range(self, client: TestClient):
        """Test GET /api/auctions/range"""
        response = client.get(
            "/api/auctions/range?start_date=2024-01-01&end_date=2024-12-31"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_auctions_with_filters(self, client: TestClient):
        """Test GET /api/auctions/range with filters"""
        response = client.get(
            "/api/auctions/range?start_date=2024-01-01&end_date=2024-12-31&instrument_type=Government+Bond&tenor=5Y"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_auctions_csv_export(self, client: TestClient):
        """Test GET /api/export/auctions.csv"""
        response = client.get(
            "/api/export/auctions.csv?start_date=2024-01-01&end_date=2024-12-31"
        )

        assert response.status_code == 200
        assert response.headers['content-type'] == 'text/csv; charset=utf-8'

        # Verify CSV has data
        content = response.content.decode()
        assert 'date,instrument_type,tenor_label' in content


class TestSecondaryAPI:
    """Test secondary trading API endpoints"""

    def test_secondary_latest(self, client: TestClient):
        """Test GET /api/secondary/latest"""
        response = client.get("/api/secondary/latest")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        # Verify structure
        record = data[0]
        assert 'date' in record
        assert 'segment' in record
        assert 'bucket_label' in record

    def test_secondary_range(self, client: TestClient):
        """Test GET /api/secondary/range"""
        response = client.get(
            "/api/secondary/range?start_date=2024-01-01&end_date=2024-12-31"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_secondary_with_filters(self, client: TestClient):
        """Test GET /api/secondary/range with filters"""
        response = client.get(
            "/api/secondary/range?start_date=2024-01-01&end_date=2024-12-31&segment=Government+Bond&bucket=Credit+Institution"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_secondary_csv_export(self, client: TestClient):
        """Test GET /api/export/secondary.csv"""
        response = client.get(
            "/api/export/secondary.csv?start_date=2024-01-01&end_date=2024-12-31"
        )

        assert response.status_code == 200
        assert response.headers['content-type'] == 'text/csv; charset=utf-8'

        # Verify CSV has data
        content = response.content.decode()
        assert 'date,segment,bucket_label' in content


class TestPolicyRatesAPI:
    """Test policy rates API endpoints"""

    def test_policy_rates_latest(self, client: TestClient):
        """Test GET /api/policy-rates/latest"""
        response = client.get("/api/policy-rates/latest")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        # Verify structure
        record = data[0]
        assert 'date' in record
        assert 'rate_name' in record
        assert 'rate' in record

    def test_policy_rates_range(self, client: TestClient):
        """Test GET /api/policy-rates/range"""
        response = client.get(
            "/api/policy-rates/range?start_date=2024-01-01&end_date=2024-12-31"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_policy_rates_with_filter(self, client: TestClient):
        """Test GET /api/policy-rates/range with rate_name filter"""
        response = client.get(
            "/api/policy-rates/range?start_date=2024-01-01&end_date=2024-12-31&rate_name=Refinancing+Rate"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_policy_rates_csv_export(self, client: TestClient):
        """Test GET /api/export/policy-rates.csv"""
        response = client.get(
            "/api/export/policy-rates.csv?start_date=2024-01-01&end_date=2024-12-31"
        )

        assert response.status_code == 200
        assert response.headers['content-type'] == 'text/csv; charset=utf-8'

        # Verify CSV has data
        content = response.content.decode()
        assert 'date,rate_name,rate' in content


class TestCoverageAPI:
    """Test coverage endpoint"""

    def test_coverage_includes_all_tables(self, client: TestClient):
        """Test GET /api/admin/coverage includes all 6 tables"""
        response = client.get("/api/admin/coverage")

        assert response.status_code == 200
        data = response.json()

        # Verify all 6 tables are present
        expected_tables = [
            'gov_yield_curve',
            'gov_yield_change_stats',
            'interbank_rates',
            'gov_auction_results',
            'gov_secondary_trading',
            'policy_rates'
        ]

        for table in expected_tables:
            assert table in data
            assert 'has_data' in data[table]
            assert 'earliest_date' in data[table]
            assert 'latest_date' in data[table]
            assert 'date_count' in data[table]

class TestDashboardFreshnessAPI:
    def test_dashboard_metrics_includes_freshness(self, client: TestClient):
        response = client.get("/api/dashboard/metrics")
        assert response.status_code == 200
        data = response.json()

        assert "as_of_date" in data
        assert "freshness" in data
        assert isinstance(data["freshness"], dict)

        expected_keys = {"yield_curve", "interbank", "bank_deposit", "bank_loan", "stress"}
        assert expected_keys.issubset(set(data["freshness"].keys()))

        for k in expected_keys:
            item = data["freshness"][k]
            assert "fill_mode" in item
            assert "note" in item

    def test_interbank_compare_includes_gap_fields(self, client: TestClient):
        response = client.get("/api/interbank/compare")
        assert response.status_code == 200
        data = response.json()

        assert "as_of_date" in data
        assert "today_gap_days" in data
        assert "note" in data


class TestUIRoutes:
    """Test UI route redirect (backend is API-only)"""

    def test_auctions_page(self, client: TestClient):
        """Test GET /auctions redirects to Next.js when requesting HTML"""
        response = client.get("/auctions", headers={"accept": "text/html"}, follow_redirects=False)

        assert response.status_code in (302, 307)
        assert response.headers.get("location", "").startswith("http")

    def test_secondary_page(self, client: TestClient):
        """Test GET /secondary redirects to Next.js when requesting HTML"""
        response = client.get("/secondary", headers={"accept": "text/html"}, follow_redirects=False)

        assert response.status_code in (302, 307)
        assert response.headers.get("location", "").startswith("http")

    def test_policy_page(self, client: TestClient):
        """Test GET /policy redirects to Next.js when requesting HTML"""
        response = client.get("/policy", headers={"accept": "text/html"}, follow_redirects=False)

        assert response.status_code in (302, 307)
        assert response.headers.get("location", "").startswith("http")
