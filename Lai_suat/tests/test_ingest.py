"""Tests for ingest idempotency."""

import pytest
import tempfile
import os
from app.db import Database
from app.ingest import Ingester
from app.parsers.deposit import DepositParser
from app.parsers.loan import LoanParser
from app.utils import get_utc_timestamp


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    db = Database(path)
    db.init_schema()

    yield db

    # Cleanup
    os.unlink(path)


@pytest.fixture
def deposit_html():
    """Load deposit fixture HTML."""
    fixture_path = 'tests/fixtures/timo_deposit.html'
    with open(fixture_path, 'r', encoding='utf-8') as f:
        return f.read()


@pytest.fixture
def loan_html():
    """Load loan fixture HTML."""
    fixture_path = 'tests/fixtures/timo_loan.html'
    with open(fixture_path, 'r', encoding='utf-8') as f:
        return f.read()


def test_ingest_idempotent_deposit(temp_db, deposit_html):
    """Test that ingesting same deposit content twice is idempotent."""
    ingester = Ingester(temp_db)

    # Parse deposit HTML
    parser = DepositParser(
        deposit_html,
        "https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/",
        get_utc_timestamp()
    )
    records, _ = parser.parse()

    # First ingestion
    result1 = ingester.ingest_records(
        records=records,
        url="https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/",
        scraped_at=get_utc_timestamp(),
        html_content=deposit_html,
        page_updated_text=None
    )

    assert result1['status'] == 'success'
    assert result1['records_count'] > 0
    assert result1['inserted'] > 0
    source_id_1 = result1['source_id']

    # Second ingestion with same content
    result2 = ingester.ingest_records(
        records=records,
        url="https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/",
        scraped_at=get_utc_timestamp(),
        html_content=deposit_html,
        page_updated_text=None
    )

    # Should be skipped due to content hash match
    assert result2['status'] == 'skipped'
    assert result2['reason'] == 'content_unchanged'
    assert result2['existing_source_id'] == source_id_1

    # Verify only one source exists
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM sources')
        count = cursor.fetchone()[0]
        assert count == 1

    # Verify observations count hasn't changed
    observations1 = temp_db.get_observations_by_source(source_id_1)
    assert len(observations1) == result1['inserted']


def test_ingest_idempotent_loan(temp_db, loan_html):
    """Test that ingesting same loan content twice is idempotent."""
    ingester = Ingester(temp_db)

    # Parse loan HTML
    parser = LoanParser(
        loan_html,
        "https://timo.vn/blogs/so-sanh-lai-suat-vay-ngan-hang-cap-nhat-moi-nhat/",
        get_utc_timestamp()
    )
    records, _ = parser.parse()

    # First ingestion
    result1 = ingester.ingest_records(
        records=records,
        url="https://timo.vn/blogs/so-sanh-lai-suat-vay-ngan-hang-cap-nhat-moi-nhat/",
        scraped_at=get_utc_timestamp(),
        html_content=loan_html,
        page_updated_text=None
    )

    assert result1['status'] == 'success'
    assert result1['records_count'] > 0
    assert result1['inserted'] > 0
    source_id_1 = result1['source_id']

    # Second ingestion with same content
    result2 = ingester.ingest_records(
        records=records,
        url="https://timo.vn/blogs/so-sanh-lai-suat-vay-ngan-hang-cap-nhat-moi-nhat/",
        scraped_at=get_utc_timestamp(),
        html_content=loan_html,
        page_updated_text=None
    )

    # Should be skipped due to content hash match
    assert result2['status'] == 'skipped'
    assert result2['reason'] == 'content_unchanged'
    assert result2['existing_source_id'] == source_id_1

    # Verify only one source exists
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM sources')
        count = cursor.fetchone()[0]
        assert count == 1

    # Verify observations count hasn't changed
    observations1 = temp_db.get_observations_by_source(source_id_1)
    assert len(observations1) == result1['inserted']


def test_ingest_different_content(temp_db, deposit_html):
    """Test that ingesting different content creates new source."""
    ingester = Ingester(temp_db)

    # Parse deposit HTML
    parser = DepositParser(
        deposit_html,
        "https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/",
        get_utc_timestamp()
    )
    records, _ = parser.parse()

    # First ingestion
    result1 = ingester.ingest_records(
        records=records,
        url="https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/",
        scraped_at=get_utc_timestamp(),
        html_content=deposit_html,
        page_updated_text=None
    )

    assert result1['status'] == 'success'
    source_id_1 = result1['source_id']

    # Second ingestion with slightly different content
    modified_html = deposit_html + "\n<!-- Small change -->"
    result2 = ingester.ingest_records(
        records=records,
        url="https://timo.vn/blogs/lai-suat-gui-tiet-kiem-ngan-hang-nao-cao-nhat/",
        scraped_at=get_utc_timestamp(),
        html_content=modified_html,
        page_updated_text=None
    )

    # Should create new source
    assert result2['status'] == 'success'
    assert result2['source_id'] != source_id_1
    source_id_2 = result2['source_id']

    # Verify two sources exist
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM sources')
        count = cursor.fetchone()[0]
        assert count == 2

    # Verify both sources have observations
    obs1 = temp_db.get_observations_by_source(source_id_1)
    obs2 = temp_db.get_observations_by_source(source_id_2)

    assert len(obs1) > 0
    assert len(obs2) > 0
    assert len(obs1) == len(obs2)  # Same records, different source
