from datetime import date, timedelta

from app.analytics.alert_engine import AlertEngine


def _seed_transmission_history(db, target: date, n: int = 40, start_value: float = 45.0, step: float = 0.1):
    """
    Seed transmission_score history on dates < target_date so z-score alerts can trigger.
    """
    for i in range(n):
        d = target - timedelta(days=i + 1)
        db.insert_transmission_metrics(d.isoformat(), {"transmission_score": start_value + (i * step)})


class TestAlertEvidenceSchema:
    def test_all_core_alerts_include_evidence(self, temp_db):
        target = date(2024, 1, 15)

        _seed_transmission_history(temp_db, target, n=40, start_value=40.0, step=0.05)

        engine = AlertEngine(temp_db)
        metrics = {
            "transmission_score": 85.0,
            "ib_on_zscore_20d": 2.6,
            "ib_on": 0.5,
            "ib_effective_date": target.isoformat(),
            "slope_10y_2y": 3.2,
            "slope_10y_2y_change_20d": 0.35,  # +35 bps
            "auction_bid_to_cover_median_20d": 1.0,
            "secondary_value_zscore_60d": -2.2,
            "policy_change_flag": True,
            "policy_refinancing": 4.5,
            "policy_rediscount": 3.0,
            "policy_base": 4.0,
            "stress_index": 72.0,
        }

        alerts = engine.detect_alerts(target_date=target, metrics=metrics, use_db_thresholds=False)
        assert isinstance(alerts, list)
        assert alerts, "Expected alerts to trigger with the supplied metrics"

        for a in alerts:
            assert "source_data" in a
            src = a["source_data"]
            assert isinstance(src, dict)
            assert "evidence" in src, f"Missing source_data.evidence for {a.get('alert_type')}"
            ev = src["evidence"]
            assert isinstance(ev, dict)
            assert "metric" in ev
            assert "method" in ev
            assert "unit" in ev

