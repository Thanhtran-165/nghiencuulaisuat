import sqlite3
import tempfile
from pathlib import Path
import sys
import os


def _lai_suat_root() -> Path:
    # vn-bond-lab/Lai_suat/tests -> vn-bond-lab/Lai_suat
    return Path(__file__).resolve().parents[1]


def test_ingest_does_not_skip_across_days_when_content_unchanged():
    """
    Regression test:
    Previously, ingestion skipped entirely when HTML content was unchanged, which
    caused missing days (e.g., 19/11) even though the scraper ran.
    """
    sys.path.insert(0, str(_lai_suat_root()))
    from app.db import Database  # type: ignore
    from app.ingest import Ingester  # type: ignore

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    db = Database(db_path)
    db.init_schema()
    ingester = Ingester(db)

    url = "https://example.com/rates"
    html = "<html><body>unchanged</body></html>"
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

    # Day 1
    res1 = ingester.ingest_records(
        records=records,
        url=url,
        scraped_at="2025-11-19T01:00:00Z",
        html_content=html,
    )
    assert res1["status"] == "success"

    # Day 2, same HTML
    res2 = ingester.ingest_records(
        records=records,
        url=url,
        scraped_at="2025-11-20T01:00:00Z",
        html_content=html,
    )
    assert res2["status"] == "success"

    con = sqlite3.connect(db_path)
    try:
        sources_cnt = con.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        assert sources_cnt == 2

        days = con.execute(
            "SELECT COUNT(DISTINCT observed_day), MIN(observed_day), MAX(observed_day) FROM observations"
        ).fetchone()
        assert days[0] == 2
        assert days[1] == "2025-11-19"
        assert days[2] == "2025-11-20"
    finally:
        con.close()
        Path(db_path).unlink(missing_ok=True)
