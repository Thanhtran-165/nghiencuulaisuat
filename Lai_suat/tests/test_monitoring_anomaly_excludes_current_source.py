import sqlite3
import tempfile
import os
from pathlib import Path
import sys


def _lai_suat_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_check_anomaly_can_exclude_current_source():
    sys.path.insert(0, str(_lai_suat_root()))
    from app.db import Database  # type: ignore
    from app.monitoring import check_anomaly  # type: ignore

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    db = Database(db_path)
    db.init_schema()

    url = "https://example.com"
    with db.get_connection() as conn:
        cur = conn.cursor()
        # Previous run
        cur.execute(
            "INSERT INTO sources (url, scraped_at, content_hash) VALUES (?, ?, ?)",
            (url, "2025-01-01T00:00:00Z", "h1"),
        )
        prev_id = cur.lastrowid
        cur.execute("UPDATE sources SET record_count_extracted = 100 WHERE id = ?", (prev_id,))

        # Current run (inserted later in the same transaction)
        cur.execute(
            "INSERT INTO sources (url, scraped_at, content_hash) VALUES (?, ?, ?)",
            (url, "2025-01-02T00:00:00Z", "h2"),
        )
        cur_id = cur.lastrowid
        cur.execute("UPDATE sources SET record_count_extracted = 10 WHERE id = ?", (cur_id,))

    # If we don't exclude, it compares against itself -> no anomaly.
    with sqlite3.connect(db_path) as conn:
        is_anom, info = check_anomaly(conn, url, new_count=10, threshold=0.30)
        assert is_anom is False
        assert info["prev_count"] == 10

        # Excluding the current source forces comparison to the previous run.
        is_anom, info = check_anomaly(conn, url, new_count=10, threshold=0.30, exclude_source_id=cur_id)
        assert is_anom is True
        assert info["prev_count"] == 100

    Path(db_path).unlink(missing_ok=True)

