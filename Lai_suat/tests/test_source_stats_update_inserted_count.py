import sqlite3
import tempfile
import os
from pathlib import Path
import sys


def _lai_suat_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_ingest_updates_sources_record_count_inserted():
    sys.path.insert(0, str(_lai_suat_root()))
    from app.db import Database  # type: ignore
    from app.ingest import Ingester  # type: ignore

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    db = Database(db_path)
    db.init_schema()
    ingester = Ingester(db)

    url = "https://example.com/rates"
    html = "<html><body>x</body></html>"
    records = [
        {
            "bank_name": "VCB",
            "product_group": "deposit",
            "series": "deposit_tai_quay",
            "term_label": "12 tháng",
            "term_months": 12,
            "rate_pct": 5.0,
            "rate_min_pct": 5.0,
            "rate_max_pct": 5.0,
            "raw_value": "5.0",
            "parse_warnings": "[]",
        }
    ]

    res = ingester.ingest_records(
        records=records,
        url=url,
        scraped_at="2025-01-01T01:00:00Z",
        html_content=html,
        strategy_used="A",
        parse_version="test",
        http_status=200,
        fetched_at="2025-01-01T01:00:00Z",
    )
    assert res["status"] == "success"
    source_id = res["source_id"]

    con = sqlite3.connect(db_path)
    try:
        row = con.execute(
            "SELECT record_count_extracted, record_count_inserted, content_hash_raw FROM sources WHERE id = ?",
            (int(source_id),),
        ).fetchone()
        assert row is not None
        assert row[0] == 1
        assert row[1] == 1
        assert row[2] is not None and len(row[2]) == 64
    finally:
        con.close()
        Path(db_path).unlink(missing_ok=True)

