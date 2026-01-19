"""
Transmission Analytics Module
Computes transmission metrics, regime buckets, and alerts for Vietnamese bond market
"""
import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import json
import statistics
import math
import os

logger = logging.getLogger(__name__)


class TransmissionAnalytics:
    """
    Compute transmission metrics and alerts from raw market data

    Metrics computed:
    - Curve level/slope/curvature
    - Liquidity stress (interbank)
    - Supply proxy (auctions)
    - Secondary demand/turnover
    - Policy rate anchor
    - Composite transmission score (0-100)
    """

    def __init__(self, db_manager):
        """
        Initialize analytics with database connection

        Args:
            db_manager: DatabaseManager instance
        """
        self.db = db_manager

    def compute_daily_metrics(self, target_date: date) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Compute all transmission metrics for a specific date

        Args:
            target_date: Date to compute metrics for

        Returns:
            Dictionary with all computed metrics
        """
        logger.info(f"Computing transmission metrics for {target_date}")

        metrics: Dict[str, Any] = {}

        # A) Curve metrics
        curve_metrics = self._compute_curve_metrics(target_date)
        metrics.update(curve_metrics)

        # B) Liquidity stress (interbank)
        liquidity_metrics = self._compute_liquidity_metrics(target_date)
        metrics.update(liquidity_metrics)

        # C) Supply proxy (auctions)
        supply_metrics = self._compute_supply_metrics(target_date)
        metrics.update(supply_metrics)

        # D) Secondary demand
        demand_metrics = self._compute_demand_metrics(target_date)
        metrics.update(demand_metrics)

        # E) Policy rates
        policy_metrics = self._compute_policy_metrics(target_date)
        metrics.update(policy_metrics)

        # F) Composite transmission score + regime bucket + alerts
        score, score_meta = self._compute_transmission_score(target_date, metrics)
        metrics["transmission_score"] = {
            "value": score,
            "sources": score_meta,
        }
        metrics["regime_bucket"] = {
            "value_text": self.map_bucket(score) if score is not None else None,
            "sources": {"method": score_meta.get("method", "weighted_zscore")},
        }
        metrics["top_drivers"] = {
            "value": 0.0,
            "sources": {"drivers": score_meta.get("top_drivers", [])},
        }
        metrics.update(self._compute_vmci_now(target_date, score))

        alerts = self.detect_alerts(metrics, target_date=target_date)

        logger.info(f"Computed {len(metrics)} transmission metrics for {target_date} (alerts={len(alerts)})")
        return metrics, alerts

    def _compute_vmci_now(self, target_date: date, score: Optional[float]) -> Dict[str, Any]:
        """
        VM-CI (V1) "Now" layer: quantile-based bucket classification + robust z-score
        computed with train-only statistics (date < target_date) to avoid leakage.
        """
        lookback = int(os.getenv("VMCI_BUCKET_LOOKBACK", "180"))
        min_n = int(os.getenv("VMCI_BUCKET_MIN_N", "60"))
        use_mad = os.getenv("VMCI_USE_MAD_ZSCORE", "false").strip().lower() in {"1", "true", "yes", "y"}

        if not isinstance(score, (int, float)):
            return {
                "vmci_now_score": {"value": None, "sources": {"note": "No transmission_score available"}},
                "vmci_now_bucket": {"value_text": None, "sources": {"note": "No transmission_score available"}},
                "vmci_now_zscore": {"value": None, "sources": {"note": "No transmission_score available"}},
            }

        # Train-only history
        rows = self.db.con.execute(
            """
            SELECT metric_value
            FROM transmission_daily_metrics
            WHERE metric_name = 'transmission_score'
              AND metric_value IS NOT NULL
              AND date < ?
            ORDER BY date DESC
            LIMIT ?
            """,
            [target_date.isoformat(), int(lookback)],
        ).fetchall()

        train = [float(r[0]) for r in rows if r and r[0] is not None]
        train_sorted = sorted(train)

        def _quantile(values_sorted: list[float], q: float) -> Optional[float]:
            if not values_sorted:
                return None
            if q <= 0:
                return float(values_sorted[0])
            if q >= 1:
                return float(values_sorted[-1])
            pos = (len(values_sorted) - 1) * q
            lo = int(pos)
            hi = min(lo + 1, len(values_sorted) - 1)
            w = pos - lo
            return float(values_sorted[lo] * (1 - w) + values_sorted[hi] * w)

        bucket = None
        p20 = p40 = p60 = p80 = None
        if len(train_sorted) >= min_n:
            p20 = _quantile(train_sorted, 0.20)
            p40 = _quantile(train_sorted, 0.40)
            p60 = _quantile(train_sorted, 0.60)
            p80 = _quantile(train_sorted, 0.80)

            # Guard: if distribution is degenerate, bucket is not meaningful yet.
            if p20 is not None and p80 is not None and abs(float(p80) - float(p20)) < 1e-9:
                bucket = None
            else:
                # Convention (consistent with existing Transmission buckets):
                # lower score = looser / easier; higher score = tighter / more stress.
                s = float(score)
                if p20 is not None and s <= p20:
                    bucket = "B0"
                elif p40 is not None and s <= p40:
                    bucket = "B1"
                elif p60 is not None and s <= p60:
                    bucket = "B2"
                elif p80 is not None and s <= p80:
                    bucket = "B3"
                else:
                    bucket = "B4"

        # Robust z-score relative to train-only history (optional MAD).
        z = None
        try:
            if len(train_sorted) >= min_n:
                if use_mad:
                    import statistics

                    med = statistics.median(train_sorted)
                    abs_dev = [abs(v - med) for v in train_sorted]
                    mad = statistics.median(abs_dev) if abs_dev else 0.0
                    denom = (mad * 1.4826) if mad and mad > 0 else 0.0
                    z = 0.0 if denom <= 0 else (float(score) - float(med)) / float(denom)
                else:
                    import statistics

                    mean = statistics.mean(train_sorted)
                    stdev = statistics.stdev(train_sorted) if len(train_sorted) > 1 else 0.0
                    z = 0.0 if stdev <= 0 else (float(score) - float(mean)) / float(stdev)
        except Exception:
            z = None

        bucket_note = None
        if len(train_sorted) < min_n:
            bucket_note = f"Calibrating buckets (need ≥{min_n} prior observations; have {len(train_sorted)})."
        elif bucket is None:
            bucket_note = "Bucket not meaningful yet (insufficient variation in history)."

        meta = {
            "lookback": int(lookback),
            "min_n": int(min_n),
            "n_train": int(len(train_sorted)),
            "p20": p20,
            "p40": p40,
            "p60": p60,
            "p80": p80,
            "z_method": "mad" if use_mad else "std",
            "note": bucket_note,
        }

        return {
            "vmci_now_score": {"value": float(score), "sources": {"definition": "VM-CI NOW = transmission_score"}},
            "vmci_now_bucket": {"value_text": bucket, "sources": meta},
            "vmci_now_zscore": {"value": z, "sources": meta},
        }

    def _compute_curve_metrics(self, target_date: date) -> Dict[str, Any]:
        """Compute curve level, slope, and curvature"""
        metrics = {}

        try:
            # Get latest yield curve data
            sql = """
            SELECT tenor_label, tenor_days, spot_rate_annual
            FROM gov_yield_curve
            WHERE date = (
                SELECT MAX(date) FROM gov_yield_curve WHERE date <= ?
            )
            ORDER BY tenor_days
            """

            result = self.db.con.execute(sql, [target_date.isoformat()]).fetchall()

            if not result:
                logger.warning(f"No yield curve data available for {target_date}")
                return {
                    'level_10y': None,
                    'slope_10y_2y': None,
                    'slope_5y_2y': None,
                    'curvature': None,
                    'curve_data_available': False
                }

            # Convert to dict by tenor
            curve_dict = {row[0]: row[2] for row in result if row[2] is not None}

            # Level: 10Y yield (or nearest)
            level_10y = self._get_nearest_tenor(curve_dict, '10Y', 3650)
            metrics['level_10y'] = level_10y

            # Slopes
            yield_2y = self._get_nearest_tenor(curve_dict, '2Y', 730)
            yield_5y = self._get_nearest_tenor(curve_dict, '5Y', 1825)
            yield_10y = self._get_nearest_tenor(curve_dict, '10Y', 3650)

            if yield_2y is not None and yield_10y is not None:
                metrics['slope_10y_2y'] = yield_10y - yield_2y
            else:
                metrics['slope_10y_2y'] = None

            if yield_2y is not None and yield_5y is not None:
                metrics['slope_5y_2y'] = yield_5y - yield_2y
            else:
                metrics['slope_5y_2y'] = None

            # Curvature: 2*(5Y) - (2Y + 10Y)
            if yield_2y is not None and yield_5y is not None and yield_10y is not None:
                metrics['curvature'] = 2 * yield_5y - (yield_2y + yield_10y)
            else:
                metrics['curvature'] = None

            metrics['curve_data_available'] = True

            # Z-scores (academic-friendly standardization)
            metrics["level_10y_zscore"] = self._compute_yield_curve_zscore("10Y", target_date, lookback_obs=60)
            metrics["slope_10y_2y_zscore"] = self._compute_curve_slope_zscore(target_date, lookback_obs=60)
            metrics.update(self._compute_curve_dynamics(target_date))

        except Exception as e:
            logger.error(f"Error computing curve metrics: {e}")
            metrics.update({
                'level_10y': None,
                'slope_10y_2y': None,
                'slope_5y_2y': None,
                'curvature': None,
                "level_10y_zscore": None,
                "slope_10y_2y_zscore": None,
                "level_10y_change_1d": None,
                "level_10y_change_1d_bps": None,
                "level_10y_realized_vol_20d": None,
                "level_10y_realized_vol_20d_bps": None,
                "slope_10y_2y_change_1d": None,
                "slope_10y_2y_change_1d_bps": None,
                "slope_10y_2y_realized_vol_20d": None,
                "slope_10y_2y_realized_vol_20d_bps": None,
                'curve_data_available': False
            })

        return metrics

    def _compute_liquidity_metrics(self, target_date: date) -> Dict[str, Any]:
        """Compute liquidity stress metrics from interbank rates"""
        metrics = {}

        try:
            # Prefer official SBV snapshots for liquidity metrics.
            latest_date = self._latest_interbank_date_with_on(target_date, prefer_source="SBV")
            if latest_date is None:
                latest_date = self._latest_interbank_date_with_on(target_date, prefer_source=None)
            if latest_date is None:
                logger.warning(f"No interbank data available for {target_date}")
                return {
                    'ib_on': None,
                    'ib_1w': None,
                    'ib_1m': None,
                    'ib_spread_1m_on': None,
                    'ib_on_zscore_20d': None,
                    'ib_1m_zscore_20d': None,
                    'ib_effective_date': None,
                    'liquidity_data_available': False
                }

            # Transparency: interbank series may not publish every calendar day; use latest snapshot <= target_date.
            metrics['ib_effective_date'] = {"value_text": latest_date.isoformat(), "sources": {"note": "latest interbank snapshot date <= target_date"}}

            # Pick one source per tenor with preference (SBV > ABO > others).
            result = self.db.con.execute(
                """
                WITH base AS (
                  SELECT date, tenor_label, rate, source, fetched_at
                  FROM interbank_rates
                  WHERE date = ? AND rate IS NOT NULL
                ),
                ranked AS (
                  SELECT
                    tenor_label,
                    rate,
                    ROW_NUMBER() OVER (
                      PARTITION BY tenor_label
                      ORDER BY
                        CASE
                          WHEN source = 'SBV' THEN 1
                          WHEN source = 'ABO' THEN 2
                          ELSE 9
                        END ASC,
                        fetched_at DESC
                    ) AS rn
                  FROM base
                )
                SELECT tenor_label, rate
                FROM ranked
                WHERE rn = 1
                """,
                [latest_date.isoformat()],
            ).fetchall()

            latest_rates = {row[0]: row[1] for row in result if row and row[0] is not None}

            metrics['ib_on'] = latest_rates.get('ON')
            metrics['ib_1w'] = latest_rates.get('1W')
            metrics['ib_1m'] = latest_rates.get('1M')

            # Spread
            if metrics['ib_1m'] and metrics['ib_on']:
                metrics['ib_spread_1m_on'] = metrics['ib_1m'] - metrics['ib_on']
            else:
                metrics['ib_spread_1m_on'] = None

            # Z-scores (20 obs ~ 1 month)
            metrics['ib_on_zscore_20d'] = self._compute_interbank_zscore('ON', target_date, lookback_obs=20)
            metrics['ib_1m_zscore_20d'] = self._compute_interbank_zscore('1M', target_date, lookback_obs=20)
            metrics['ib_spread_1m_on_zscore_60d'] = self._compute_interbank_spread_zscore(
                short_tenor="1M",
                long_tenor="ON",
                target_date=target_date,
                lookback_obs=60,
            )

            metrics['liquidity_data_available'] = True
            # Common alias used by score/drivers
            metrics['ib_on_zscore'] = metrics.get('ib_on_zscore_20d')
            metrics['corr_10y_ib_on_change_60d'] = self._compute_corr_yield_ib_changes(
                yield_tenor="10Y",
                ib_tenor="ON",
                target_date=target_date,
                window=60,
            )
            metrics['corr_10y_ib_on_change_20d'] = self._compute_corr_yield_ib_changes(
                yield_tenor="10Y",
                ib_tenor="ON",
                target_date=target_date,
                window=20,
            )

        except Exception as e:
            logger.error(f"Error computing liquidity metrics: {e}")
            metrics.update({
                'ib_on': None,
                'ib_1w': None,
                'ib_1m': None,
                'ib_spread_1m_on': None,
                'ib_on_zscore_20d': None,
                'ib_1m_zscore_20d': None,
                'ib_spread_1m_on_zscore_60d': None,
                'corr_10y_ib_on_change_60d': None,
                'corr_10y_ib_on_change_20d': None,
                'ib_effective_date': None,
                'liquidity_data_available': False
            })

        return metrics

    def _latest_interbank_date_with_on(self, target_date: date, prefer_source: Optional[str] = "SBV") -> Optional[date]:
        """
        Find the latest interbank snapshot date (<= target_date) that contains an ON rate.
        If prefer_source is set, try that source first, then fall back to any source.
        """
        try:
            if prefer_source:
                row = self.db.con.execute(
                    """
                    SELECT MAX(date)
                    FROM interbank_rates
                    WHERE date <= ?
                      AND source = ?
                      AND tenor_label = 'ON'
                      AND rate IS NOT NULL
                    """,
                    [target_date.isoformat(), prefer_source],
                ).fetchone()
                if row and row[0] is not None:
                    return row[0]

            row = self.db.con.execute(
                """
                SELECT MAX(date)
                FROM interbank_rates
                WHERE date <= ?
                  AND tenor_label = 'ON'
                  AND rate IS NOT NULL
                """,
                [target_date.isoformat()],
            ).fetchone()
            if not row or row[0] is None:
                return None
            return row[0]
        except Exception:
            return None

    def _compute_supply_metrics(self, target_date: date) -> Dict[str, Any]:
        """Compute supply proxy metrics from auction results"""
        metrics = {}

        try:
            sold_series = self._fetch_daily_series(
                """
                SELECT date, SUM(amount_sold) AS v
                FROM gov_auction_results
                WHERE date <= ? AND amount_sold IS NOT NULL
                GROUP BY date
                ORDER BY date DESC
                LIMIT ?
                """,
                [target_date.isoformat(), 120],
            )
            try:
                btc_series = self._fetch_daily_series(
                    """
                    SELECT date, median(bid_to_cover) AS v
                    FROM gov_auction_results
                    WHERE date <= ? AND bid_to_cover IS NOT NULL
                    GROUP BY date
                    ORDER BY date DESC
                    LIMIT ?
                    """,
                    [target_date.isoformat(), 120],
                )
            except Exception:
                # Older DuckDB versions may not expose median(); fall back to quantile_cont.
                btc_series = self._fetch_daily_series(
                    """
                    SELECT date, quantile_cont(bid_to_cover, 0.5) AS v
                    FROM gov_auction_results
                    WHERE date <= ? AND bid_to_cover IS NOT NULL
                    GROUP BY date
                    ORDER BY date DESC
                    LIMIT ?
                    """,
                    [target_date.isoformat(), 120],
                )

            if not sold_series and not btc_series:
                logger.warning(f"No auction data available for {target_date}")
                return {
                    'auction_sold_total_5d': None,
                    'auction_bid_to_cover_median_20d': None,
                    'auction_cutoff_yield_change_5d': None,
                    'auction_sold_total_5d_zscore': None,
                    'auction_btc_daily_median': None,
                    'auction_btc_daily_median_zscore_60d': None,
                    'supply_data_available': False
                }

            sold_values = [v for _, v in sold_series if isinstance(v, (int, float))]
            btc_values = [v for _, v in btc_series if isinstance(v, (int, float))]

            # Use the latest available auction sessions (up to 5). Early in the DB lifecycle,
            # requiring a full 5 observations makes the UI look "missing" even though data exists.
            metrics["auction_sold_total_5d"] = float(sum(sold_values[: min(5, len(sold_values))])) if sold_values else None
            metrics["auction_sold_total_5d_zscore"] = self._zscore_latest(self._rolling_sum_series(sold_values, window=5), min_obs=20)

            metrics["auction_btc_daily_median"] = btc_values[0] if btc_values else None
            metrics["auction_btc_daily_median_zscore_60d"] = self._zscore_latest(btc_values[:60], min_obs=20) if btc_values else None

            # Backward-compatible descriptive statistic (median of latest 20 daily medians)
            metrics['auction_bid_to_cover_median_20d'] = statistics.median(btc_values[:20]) if len(btc_values) >= 1 else None

            # Cutoff yield change (last 5 sessions, by tenor) – keep simple for now
            sql_cutoff = """
            SELECT date, tenor_label, AVG(cut_off_yield) AS y
            FROM gov_auction_results
            WHERE date <= ? AND cut_off_yield IS NOT NULL AND tenor_label IN ('5Y','10Y')
            GROUP BY date, tenor_label
            ORDER BY date DESC
            LIMIT 50
            """
            cutoff_rows = self.db.con.execute(sql_cutoff, [target_date.isoformat()]).fetchall()
            cutoff_changes = []
            for tenor in ['5Y', '10Y']:
                tenor_cutoffs = [row[2] for row in cutoff_rows if row[2] is not None and row[1] == tenor][:5]
                if len(tenor_cutoffs) >= 2:
                    cutoff_changes.append(tenor_cutoffs[0] - tenor_cutoffs[-1])
            metrics['auction_cutoff_yield_change_5d'] = (sum(cutoff_changes) / len(cutoff_changes)) if cutoff_changes else None

            metrics['supply_data_available'] = True

        except Exception as e:
            logger.error(f"Error computing supply metrics: {e}")
            metrics.update({
                'auction_sold_total_5d': None,
                'auction_bid_to_cover_median_20d': None,
                'auction_cutoff_yield_change_5d': None,
                'auction_sold_total_5d_zscore': None,
                'auction_btc_daily_median': None,
                'auction_btc_daily_median_zscore_60d': None,
                'supply_data_available': False
            })

        return metrics

    def _compute_demand_metrics(self, target_date: date) -> Dict[str, Any]:
        """Compute secondary market demand metrics"""
        metrics = {}

        try:
            value_series = self._fetch_daily_series(
                """
                SELECT date, SUM(value) AS v
                FROM gov_secondary_trading
                WHERE date <= ? AND value IS NOT NULL
                GROUP BY date
                ORDER BY date DESC
                LIMIT ?
                """,
                [target_date.isoformat(), 200],
            )

            if not value_series:
                logger.warning(f"No secondary trading data available for {target_date}")
                return {
                    'secondary_value_total_5d': None,
                    'secondary_value_zscore_60d': None,
                    'secondary_value_total_5d_zscore': None,
                    'demand_data_available': False
                }

            values = [v for _, v in value_series if isinstance(v, (int, float))]
            # Same rationale as auctions: sum the latest available sessions up to 5.
            metrics['secondary_value_total_5d'] = float(sum(values[: min(5, len(values))])) if values else None
            metrics['secondary_value_total_5d_zscore'] = self._zscore_latest(self._rolling_sum_series(values, window=5), min_obs=20)

            # Keep existing single-day z-score for compatibility
            metrics['secondary_value_zscore_60d'] = self._zscore_latest(values[:60], min_obs=20)

            metrics['demand_data_available'] = True

        except Exception as e:
            logger.error(f"Error computing demand metrics: {e}")
            metrics.update({
                'secondary_value_total_5d': None,
                'secondary_value_zscore_60d': None,
                'secondary_value_total_5d_zscore': None,
                'demand_data_available': False
            })

        return metrics

    def _compute_policy_metrics(self, target_date: date) -> Dict[str, Any]:
        """Compute policy rate anchor metrics"""
        metrics = {}

        try:
            # Get latest policy rates
            sql = """
            SELECT rate_name, rate
            FROM policy_rates
            WHERE date = (
                SELECT MAX(date) FROM policy_rates WHERE date <= ?
            )
            ORDER BY rate_name
            """

            result = self.db.con.execute(sql, [target_date.isoformat()]).fetchall()

            if not result:
                logger.warning(f"No policy rate data available for {target_date}")
                return {
                    'policy_refinancing': None,
                    'policy_rediscount': None,
                    'policy_base': None,
                    'policy_rate_latest': None,
                    'policy_change_flag': False,
                    'policy_data_available': False
                }

            # Extract rates
            policy_dict = {row[0]: row[1] for row in result}

            metrics['policy_refinancing'] = policy_dict.get('Refinancing Rate')
            metrics['policy_rediscount'] = policy_dict.get('Rediscount Rate')
            metrics['policy_base'] = policy_dict.get('Base Rate')
            metrics['policy_rate_latest'] = (
                metrics.get('policy_refinancing')
                or metrics.get('policy_base')
                or metrics.get('policy_rediscount')
            )

            # Check for policy change (vs previous day)
            yesterday = target_date - timedelta(days=1)

            sql_prev = """
            SELECT rate_name, rate
            FROM policy_rates
            WHERE date = (
                SELECT MAX(date) FROM policy_rates WHERE date <= ?
            )
            """

            result_prev = self.db.con.execute(sql_prev, [yesterday.isoformat()]).fetchall()

            if result_prev:
                policy_prev = {row[0]: row[1] for row in result_prev}

                # Check if any rate changed
                for rate_name in policy_dict:
                    if rate_name in policy_prev:
                        if abs(policy_dict[rate_name] - policy_prev[rate_name]) > 0.01:  # > 1 basis point
                            metrics['policy_change_flag'] = True
                            break
                else:
                    metrics['policy_change_flag'] = False
            else:
                metrics['policy_change_flag'] = False

            metrics['policy_data_available'] = True
            metrics['policy_spread_ib_on'] = None
            try:
                if metrics.get("policy_rate_latest") is not None:
                    latest_ib_date = self._latest_available_date("interbank_rates", target_date)
                    if latest_ib_date is not None:
                        ib_on = self.db.con.execute(
                            """
                            SELECT AVG(rate) AS v
                            FROM interbank_rates
                            WHERE tenor_label = 'ON' AND date = ? AND rate IS NOT NULL
                            """,
                            [latest_ib_date.isoformat()],
                        ).fetchone()[0]
                        if isinstance(ib_on, (int, float)):
                            metrics["policy_spread_ib_on"] = float(ib_on) - float(metrics["policy_rate_latest"])
            except Exception:
                metrics["policy_spread_ib_on"] = None
            metrics['policy_spread_ib_on_zscore_60d'] = self._compute_policy_spread_zscore(
                target_date,
                lookback_obs=60,
            )
            # Simple term-premium proxy: 10Y yield - policy anchor
            try:
                if metrics.get("policy_rate_latest") is not None:
                    y10 = self._get_latest_yield_for_tenor("10Y", target_date)
                    if isinstance(y10, (int, float)):
                        metrics["term_premium_10y_policy"] = float(y10) - float(metrics["policy_rate_latest"])
                    else:
                        metrics["term_premium_10y_policy"] = None
                else:
                    metrics["term_premium_10y_policy"] = None
            except Exception:
                metrics["term_premium_10y_policy"] = None

        except Exception as e:
            logger.error(f"Error computing policy metrics: {e}")
            metrics.update({
                'policy_refinancing': None,
                'policy_rediscount': None,
                'policy_base': None,
                'policy_rate_latest': None,
                'policy_change_flag': False,
                'policy_spread_ib_on': None,
                'policy_spread_ib_on_zscore_60d': None,
                'term_premium_10y_policy': None,
                'policy_data_available': False
            })

        return metrics

    def _compute_transmission_score(self, target_date: date, metrics: Dict[str, Any]) -> Tuple[Optional[float], Dict[str, Any]]:
        """
        Compute composite transmission score (0-100)

        Higher score = higher stress
        """
        def winsorize(value: float, limit: float = 3.0) -> float:
            return max(-limit, min(limit, value))

        method = os.getenv("TRANSMISSION_SCORE_METHOD", "weighted_zscore_logistic").strip().lower()
        logistic_k = float(os.getenv("TRANSMISSION_LOGISTIC_K", "1.2"))
        asym_pos = float(os.getenv("TRANSMISSION_ASYM_POS", "1.0"))
        asym_neg = float(os.getenv("TRANSMISSION_ASYM_NEG", "1.0"))

        # Academic-friendly: signed, weighted z-score composite.
        # Convention: positive signed_z => tighter / more stress.
        components = [
            {"key": "yield_level", "z": metrics.get("level_10y_zscore"), "sign": +1.0, "weight": 1.0},
            {"key": "curve_slope", "z": metrics.get("slope_10y_2y_zscore"), "sign": +1.0, "weight": 0.5},
            {"key": "interbank_stress", "z": metrics.get("ib_on_zscore") or metrics.get("ib_on_zscore_20d"), "sign": +1.0, "weight": 1.0},
            {"key": "auction_demand", "z": metrics.get("auction_btc_daily_median_zscore_60d"), "sign": -1.0, "weight": 1.0},
            {"key": "secondary_liquidity", "z": metrics.get("secondary_value_total_5d_zscore") or metrics.get("secondary_value_zscore_60d"), "sign": -1.0, "weight": 1.0},
            {"key": "policy_spread", "z": metrics.get("policy_spread_ib_on_zscore_60d"), "sign": +1.0, "weight": 0.5},
        ]

        dynamic_weights: Optional[dict[str, float]] = None
        pca_meta: dict[str, Any] = {}
        if method in {"pca_dynamic", "pca"}:
            dynamic_weights, pca_meta = self._compute_dynamic_pca_weights(
                target_date=target_date,
                current_metrics=metrics,
                components=components,
                lookback_days=int(os.getenv("TRANSMISSION_PCA_LOOKBACK_DAYS", "252")),
                min_rows=int(os.getenv("TRANSMISSION_PCA_MIN_ROWS", "80")),
            )

        used: list[dict[str, Any]] = []
        weighted = []
        weight_sum = 0.0
        for c in components:
            z = c["z"]
            if not isinstance(z, (int, float)):
                continue
            signed = winsorize(float(z) * float(c["sign"]))
            # Optional asymmetry: treat tightening more aggressively (or vice versa).
            if signed >= 0:
                signed *= asym_pos
            else:
                signed *= asym_neg

            w = float(dynamic_weights.get(c["key"], c["weight"])) if dynamic_weights else float(c["weight"])
            used.append(
                {
                    "key": c["key"],
                    "z": float(z),
                    "signed_z": signed,
                    "sign": float(c["sign"]),
                    "weight": w,
                    "contribution": w * signed,
                }
            )
            weighted.append(w * signed)
            weight_sum += w

        if weight_sum <= 0 or len(used) < 3:
            # Early-phase / fresh DB: z-score history may be insufficient even if data is present.
            # Return a neutral score (50) so the UI shows a regime bucket and the series can start
            # building immediately; the score becomes data-driven once z-scores are available.
            return 50.0, {
                "method": f"{method}_bootstrap_neutral",
                "note": "Insufficient z-score history; returning neutral score until enough observations accumulate.",
                "components_used": used,
                "top_drivers": [],
            }

        avg_z = sum(weighted) / weight_sum
        if method in {"weighted_zscore", "pca_dynamic", "pca"}:
            score = 50 + 10 * avg_z
        else:
            # Default: logistic (bounded, non-linear; 0 -> 50).
            score = 100.0 / (1.0 + math.exp(-logistic_k * avg_z))
        score = max(0.0, min(100.0, score))

        top_drivers = sorted(used, key=lambda d: abs(float(d["contribution"])), reverse=True)[:3]
        # Stable, UI-friendly format
        top_drivers_ui = [
            {
                "name": d["key"],
                "contribution": float(d["contribution"]),
                "direction": "↑" if float(d["contribution"]) > 0 else "↓",
                "z": float(d["z"]),
                "signed_z": float(d["signed_z"]),
                "weight": float(d["weight"]),
            }
            for d in top_drivers
        ]

        return round(score, 2), {
            "method": method,
            "weight_sum": weight_sum,
            "avg_z": avg_z,
            "logistic_k": logistic_k if method not in {"weighted_zscore", "pca_dynamic", "pca"} else None,
            "asym_pos": asym_pos,
            "asym_neg": asym_neg,
            "dynamic_weights": dynamic_weights,
            **pca_meta,
            "components_used": used,
            "top_drivers": top_drivers_ui,
        }

    def _compute_curve_dynamics(self, target_date: date) -> Dict[str, Any]:
        """
        Compute yield/slope daily changes and realized volatility from available curve data.

        Note: Uses observed curve dates; not calendar-day interpolation.
        """
        metrics: Dict[str, Any] = {
            "level_10y_change_1d": None,
            "level_10y_change_1d_bps": None,
            "level_10y_realized_vol_20d": None,
            "level_10y_realized_vol_20d_bps": None,
            "slope_10y_2y_change_1d": None,
            "slope_10y_2y_change_1d_bps": None,
            "slope_10y_2y_realized_vol_20d": None,
            "slope_10y_2y_realized_vol_20d_bps": None,
        }

        y10_series = self._fetch_daily_series(
            """
            SELECT date, AVG(spot_rate_annual) AS v
            FROM gov_yield_curve
            WHERE tenor_label = '10Y' AND date <= ? AND spot_rate_annual IS NOT NULL
            GROUP BY date
            ORDER BY date DESC
            LIMIT 80
            """,
            [target_date.isoformat()],
        )
        y10_values = [v for _, v in y10_series if isinstance(v, (int, float))]
        if len(y10_values) >= 2:
            delta = float(y10_values[0]) - float(y10_values[1])
            metrics["level_10y_change_1d"] = delta
            metrics["level_10y_change_1d_bps"] = delta * 100.0
        vol = self._compute_realized_volatility_from_levels_desc(y10_values, window_changes=20)
        if vol is not None:
            metrics["level_10y_realized_vol_20d"] = vol
            metrics["level_10y_realized_vol_20d_bps"] = vol * 100.0

        slopes_series = self._fetch_curve_slope_series(target_date=target_date, lookback_obs=80)
        slopes_values = [v for _, v in slopes_series if isinstance(v, (int, float))]
        if len(slopes_values) >= 2:
            delta = float(slopes_values[0]) - float(slopes_values[1])
            metrics["slope_10y_2y_change_1d"] = delta
            metrics["slope_10y_2y_change_1d_bps"] = delta * 100.0
        slope_vol = self._compute_realized_volatility_from_levels_desc(slopes_values, window_changes=20)
        if slope_vol is not None:
            metrics["slope_10y_2y_realized_vol_20d"] = slope_vol
            metrics["slope_10y_2y_realized_vol_20d_bps"] = slope_vol * 100.0

        return metrics

    def _fetch_curve_slope_series(self, target_date: date, lookback_obs: int) -> list[tuple[date, float]]:
        rows = self.db.con.execute(
            """
            SELECT
                date,
                AVG(CASE WHEN tenor_label = '10Y' THEN spot_rate_annual END) AS y10,
                AVG(CASE WHEN tenor_label = '2Y' THEN spot_rate_annual END) AS y2
            FROM gov_yield_curve
            WHERE date <= ?
              AND tenor_label IN ('2Y','10Y')
              AND spot_rate_annual IS NOT NULL
            GROUP BY date
            ORDER BY date DESC
            LIMIT ?
            """,
            [target_date.isoformat(), int(lookback_obs)],
        ).fetchall()
        out: list[tuple[date, float]] = []
        for d, y10, y2 in rows:
            if d is None or y10 is None or y2 is None:
                continue
            out.append((d, float(y10) - float(y2)))
        return out

    def _compute_realized_volatility_from_levels_desc(
        self,
        values_desc: list[float],
        window_changes: int,
    ) -> Optional[float]:
        values = [float(v) for v in values_desc if isinstance(v, (int, float))]
        if len(values) < window_changes + 1:
            return None
        changes = [values[i] - values[i + 1] for i in range(window_changes)]
        stdev = statistics.stdev(changes) if len(changes) > 1 else 0.0
        return float(stdev)

    def _compute_corr_yield_ib_changes(
        self,
        yield_tenor: str,
        ib_tenor: str,
        target_date: date,
        window: int,
    ) -> Optional[float]:
        """
        Rolling correlation between daily changes:
          Δyield(yield_tenor) vs Δinterbank(ib_tenor)
        computed on the latest available overlap window.
        """
        # Fetch a bit more than window to survive missing dates.
        limit = max(120, window + 30)

        yield_rows = self._fetch_daily_series(
            """
            SELECT date, AVG(spot_rate_annual) AS v
            FROM gov_yield_curve
            WHERE tenor_label = ? AND date <= ? AND spot_rate_annual IS NOT NULL
            GROUP BY date
            ORDER BY date DESC
            LIMIT ?
            """,
            [yield_tenor, target_date.isoformat(), int(limit)],
        )
        ib_rows = self._fetch_daily_series(
            """
            SELECT date, AVG(rate) AS v
            FROM interbank_rates
            WHERE tenor_label = ? AND date <= ? AND rate IS NOT NULL
            GROUP BY date
            ORDER BY date DESC
            LIMIT ?
            """,
            [ib_tenor, target_date.isoformat(), int(limit)],
        )

        yield_map = {d: float(v) for d, v in yield_rows if d is not None and isinstance(v, (int, float))}
        ib_map = {d: float(v) for d, v in ib_rows if d is not None and isinstance(v, (int, float))}

        overlap_dates = sorted(set(yield_map.keys()) & set(ib_map.keys()))
        if len(overlap_dates) < window + 2:
            return None

        # Use the latest overlap dates.
        overlap_dates = overlap_dates[-(window + 2) :]

        y_changes: list[float] = []
        ib_changes: list[float] = []
        for i in range(1, len(overlap_dates)):
            d0 = overlap_dates[i - 1]
            d1 = overlap_dates[i]
            y_changes.append(yield_map[d1] - yield_map[d0])
            ib_changes.append(ib_map[d1] - ib_map[d0])

        if len(y_changes) < 20:
            return None

        y = y_changes[-window:]
        x = ib_changes[-window:]
        if len(y) != len(x) or len(y) < 20:
            return None

        mean_y = statistics.mean(y)
        mean_x = statistics.mean(x)
        std_y = statistics.stdev(y) if len(y) > 1 else 0.0
        std_x = statistics.stdev(x) if len(x) > 1 else 0.0
        if std_x <= 0 or std_y <= 0:
            return None
        cov = sum((yi - mean_y) * (xi - mean_x) for yi, xi in zip(y, x)) / (len(y) - 1)
        return float(cov / (std_x * std_y))

    def _compute_dynamic_pca_weights(
        self,
        target_date: date,
        current_metrics: Dict[str, Any],
        components: list[dict[str, Any]],
        lookback_days: int,
        min_rows: int,
    ) -> tuple[Optional[dict[str, float]], dict[str, Any]]:
        """
        Dynamic weights via rolling PCA on signed z-score components stored in transmission_daily_metrics.

        Falls back to None if not enough history or numpy is unavailable.
        """
        try:
            import numpy as np  # type: ignore
        except Exception:
            return None, {"pca_enabled": False, "pca_reason": "numpy_unavailable"}

        # Map component keys -> underlying metric_name in DB (z-scores)
        key_to_metric = {
            "yield_level": ("level_10y_zscore", +1.0),
            "curve_slope": ("slope_10y_2y_zscore", +1.0),
            "interbank_stress": ("ib_on_zscore_20d", +1.0),
            "auction_demand": ("auction_btc_daily_median_zscore_60d", -1.0),
            "secondary_liquidity": ("secondary_value_zscore_60d", -1.0),
            "policy_spread": ("policy_spread_ib_on_zscore_60d", +1.0),
        }

        # Only keep components that exist in the current spec.
        keys = [c["key"] for c in components if c.get("key") in key_to_metric]
        if len(keys) < 3:
            return None, {"pca_enabled": False, "pca_reason": "insufficient_components"}

        per_key_series: dict[str, dict[date, float]] = {}
        for k in keys:
            metric_name, sign = key_to_metric[k]
            rows = self.db.con.execute(
                """
                SELECT date, metric_value
                FROM transmission_daily_metrics
                WHERE metric_name = ?
                  AND date <= ?
                  AND metric_value IS NOT NULL
                ORDER BY date DESC
                LIMIT ?
                """,
                [metric_name, target_date.isoformat(), int(lookback_days)],
            ).fetchall()
            series = {d: float(v) * float(sign) for d, v in rows if d is not None and isinstance(v, (int, float))}

            # Inject current day's computed z if present (not yet inserted).
            current_z = current_metrics.get(metric_name)
            if isinstance(current_z, (int, float)):
                series[target_date] = float(current_z) * float(sign)

            per_key_series[k] = series

        common_dates = None
        for series in per_key_series.values():
            dates = set(series.keys())
            common_dates = dates if common_dates is None else (common_dates & dates)
        if not common_dates:
            return None, {"pca_enabled": False, "pca_reason": "no_overlap"}

        dates_sorted = sorted(common_dates)
        # Use most recent rows
        if len(dates_sorted) > lookback_days:
            dates_sorted = dates_sorted[-lookback_days:]
        if len(dates_sorted) < min_rows:
            return None, {"pca_enabled": False, "pca_reason": "not_enough_rows", "rows": len(dates_sorted)}

        X = np.array([[per_key_series[k][d] for k in keys] for d in dates_sorted], dtype=float)

        # Standardize columns (PCA on correlation matrix)
        X = X - X.mean(axis=0, keepdims=True)
        col_std = X.std(axis=0, ddof=1)
        col_std[col_std == 0] = 1.0
        Xs = X / col_std

        cov = np.cov(Xs, rowvar=False)
        eigvals, eigvecs = np.linalg.eigh(cov)
        idx = int(np.argmax(eigvals))
        pc1 = eigvecs[:, idx]

        weights = np.abs(pc1)
        wsum = float(weights.sum())
        if wsum <= 0:
            return None, {"pca_enabled": False, "pca_reason": "zero_weights"}

        weights = weights / wsum
        out = {k: float(weights[i]) for i, k in enumerate(keys)}

        total_var = float(eigvals.sum()) if float(eigvals.sum()) > 0 else 0.0
        explained = float(eigvals[idx] / total_var) if total_var > 0 else None

        return out, {
            "pca_enabled": True,
            "pca_rows": len(dates_sorted),
            "pca_explained_variance": explained,
        }

    def _get_latest_yield_for_tenor(self, tenor_label: str, target_date: date) -> Optional[float]:
        try:
            row = self.db.con.execute(
                """
                SELECT AVG(spot_rate_annual) AS v
                FROM gov_yield_curve
                WHERE tenor_label = ? AND date = (
                    SELECT MAX(date) FROM gov_yield_curve WHERE tenor_label = ? AND date <= ?
                )
                """,
                [tenor_label, tenor_label, target_date.isoformat()],
            ).fetchone()
            if not row or row[0] is None:
                return None
            return float(row[0])
        except Exception:
            return None

    def _get_nearest_tenor(self, curve_dict: Dict[str, float], target_tenor: str, target_days: int) -> Optional[float]:
        """Get yield for nearest tenor"""
        if target_tenor in curve_dict:
            return curve_dict[target_tenor]

        def tenor_to_days(label: str) -> Optional[int]:
            try:
                label = label.strip().upper()
                if label.endswith("Y"):
                    return int(float(label[:-1]) * 365)
                if label.endswith("M"):
                    return int(float(label[:-1]) * 30)
                if label.endswith("W"):
                    return int(float(label[:-1]) * 7)
                if label.endswith("D"):
                    return int(float(label[:-1]))
            except Exception:
                return None
            return None

        best_label = None
        best_dist = None
        for label in curve_dict.keys():
            days = tenor_to_days(label)
            if days is None:
                continue
            dist = abs(days - target_days)
            if best_dist is None or dist < best_dist:
                best_label = label
                best_dist = dist

        if best_label is None:
            return None
        return curve_dict.get(best_label)

    def _latest_available_date(self, table: str, target_date: date) -> Optional[date]:
        try:
            row = self.db.con.execute(
                f"SELECT MAX(date) FROM {table} WHERE date <= ?",
                [target_date.isoformat()],
            ).fetchone()
            if not row or row[0] is None:
                return None
            return row[0]
        except Exception:
            return None

    def _fetch_daily_series(self, sql: str, params: list[Any]) -> list[tuple[date, float]]:
        rows = self.db.con.execute(sql, params).fetchall()
        out: list[tuple[date, float]] = []
        for row in rows:
            if row[0] is None:
                continue
            out.append((row[0], row[1]))
        return out

    def _zscore_latest(self, values_desc: list[float], min_obs: int = 20) -> Optional[float]:
        values = [float(v) for v in values_desc if isinstance(v, (int, float))]
        if len(values) < min_obs:
            return None
        latest = values[0]
        stdev = statistics.stdev(values) if len(values) > 1 else 0.0
        if stdev <= 0:
            return 0.0
        mean = statistics.mean(values)
        return (latest - mean) / stdev

    def _rolling_sum_latest(self, values_desc: list[float], window: int) -> Optional[float]:
        values = [float(v) for v in values_desc if isinstance(v, (int, float))]
        if len(values) < window:
            return None
        return float(sum(values[:window]))

    def _rolling_sum_series(self, values_desc: list[float], window: int) -> list[float]:
        values = [float(v) for v in values_desc if isinstance(v, (int, float))]
        if len(values) < window:
            return []
        return [float(sum(values[i : i + window])) for i in range(0, len(values) - window + 1)]

    def _compute_yield_curve_zscore(self, tenor_label: str, target_date: date, lookback_obs: int) -> Optional[float]:
        series = self._fetch_daily_series(
            """
            SELECT date, AVG(spot_rate_annual) AS v
            FROM gov_yield_curve
            WHERE tenor_label = ? AND date <= ? AND spot_rate_annual IS NOT NULL
            GROUP BY date
            ORDER BY date DESC
            LIMIT ?
            """,
            [tenor_label, target_date.isoformat(), int(lookback_obs)],
        )
        values = [v for _, v in series if isinstance(v, (int, float))]
        return self._zscore_latest(values, min_obs=min(20, lookback_obs))

    def _compute_curve_slope_zscore(self, target_date: date, lookback_obs: int) -> Optional[float]:
        rows = self.db.con.execute(
            """
            SELECT
                date,
                AVG(CASE WHEN tenor_label = '10Y' THEN spot_rate_annual END) AS y10,
                AVG(CASE WHEN tenor_label = '2Y' THEN spot_rate_annual END) AS y2
            FROM gov_yield_curve
            WHERE date <= ?
              AND tenor_label IN ('2Y','10Y')
              AND spot_rate_annual IS NOT NULL
            GROUP BY date
            ORDER BY date DESC
            LIMIT ?
            """,
            [target_date.isoformat(), int(lookback_obs)],
        ).fetchall()
        slopes: list[float] = []
        for _, y10, y2 in rows:
            if y10 is None or y2 is None:
                continue
            slopes.append(float(y10) - float(y2))
        return self._zscore_latest(slopes, min_obs=min(20, lookback_obs))

    def _compute_interbank_zscore(self, tenor_label: str, target_date: date, lookback_obs: int) -> Optional[float]:
        series = self._fetch_daily_series(
            """
            SELECT date, AVG(rate) AS v
            FROM interbank_rates
            WHERE tenor_label = ? AND date <= ? AND rate IS NOT NULL
            GROUP BY date
            ORDER BY date DESC
            LIMIT ?
            """,
            [tenor_label, target_date.isoformat(), int(lookback_obs)],
        )
        values = [v for _, v in series if isinstance(v, (int, float))]
        return self._zscore_latest(values, min_obs=min(20, lookback_obs))

    def _compute_interbank_spread_zscore(
        self,
        short_tenor: str,
        long_tenor: str,
        target_date: date,
        lookback_obs: int,
    ) -> Optional[float]:
        short_series = self._fetch_daily_series(
            """
            SELECT date, AVG(rate) AS v
            FROM interbank_rates
            WHERE tenor_label = ? AND date <= ? AND rate IS NOT NULL
            GROUP BY date
            ORDER BY date DESC
            LIMIT ?
            """,
            [short_tenor, target_date.isoformat(), int(lookback_obs)],
        )
        long_series = self._fetch_daily_series(
            """
            SELECT date, AVG(rate) AS v
            FROM interbank_rates
            WHERE tenor_label = ? AND date <= ? AND rate IS NOT NULL
            GROUP BY date
            ORDER BY date DESC
            LIMIT ?
            """,
            [long_tenor, target_date.isoformat(), int(lookback_obs)],
        )
        short_map = {d: v for d, v in short_series if isinstance(v, (int, float))}
        long_map = {d: v for d, v in long_series if isinstance(v, (int, float))}
        spreads: list[float] = []
        for d, v in short_series:
            if d in short_map and d in long_map:
                spreads.append(float(short_map[d]) - float(long_map[d]))
        return self._zscore_latest(spreads, min_obs=min(20, lookback_obs))

    def _compute_policy_spread_zscore(self, target_date: date, lookback_obs: int) -> Optional[float]:
        # Interbank ON series (dates drive the spread series)
        ib_series = self._fetch_daily_series(
            """
            SELECT date, AVG(rate) AS v
            FROM interbank_rates
            WHERE tenor_label = 'ON' AND date <= ? AND rate IS NOT NULL
            GROUP BY date
            ORDER BY date DESC
            LIMIT ?
            """,
            [target_date.isoformat(), int(max(lookback_obs, 90))],
        )
        if not ib_series:
            return None

        policy_rows = self.db.con.execute(
            """
            SELECT
                date,
                MAX(CASE WHEN rate_name = 'Refinancing Rate' THEN rate END) AS refinancing,
                MAX(CASE WHEN rate_name = 'Base Rate' THEN rate END) AS base,
                MAX(CASE WHEN rate_name = 'Rediscount Rate' THEN rate END) AS rediscount
            FROM policy_rates
            WHERE date <= ? AND rate IS NOT NULL
            GROUP BY date
            ORDER BY date ASC
            """,
            [target_date.isoformat()],
        ).fetchall()
        if not policy_rows:
            return None

        # Build an "effective policy anchor" series (forward-fill by date).
        policy_points: list[tuple[date, float]] = []
        for d, refinancing, base, rediscount in policy_rows:
            anchor = refinancing if refinancing is not None else base if base is not None else rediscount
            if anchor is None:
                continue
            policy_points.append((d, float(anchor)))

        if not policy_points:
            return None

        policy_points.sort(key=lambda x: x[0])
        spreads: list[float] = []
        last_anchor: Optional[float] = None
        policy_idx = 0
        for ib_date, ib_on in reversed(ib_series):  # ascending for forward fill
            while policy_idx < len(policy_points) and policy_points[policy_idx][0] <= ib_date:
                last_anchor = policy_points[policy_idx][1]
                policy_idx += 1
            if last_anchor is None or not isinstance(ib_on, (int, float)):
                continue
            spreads.append(float(ib_on) - float(last_anchor))

        spreads_desc = list(reversed(spreads))[: int(lookback_obs)]
        return self._zscore_latest(spreads_desc, min_obs=min(20, lookback_obs))

    def _compute_slope_zscore(self, slope_name: str, target_date: date, lookback_days: int) -> Optional[float]:
        """Compute z-score for slope metric"""
        try:
            # Get historical slopes
            # This is a simplified version - in practice you'd compute historical slopes
            return 0.0  # Placeholder
        except:
            return None

    def _compute_btc_zscore(self, target_date: date, lookback_days: int) -> Optional[float]:
        """Compute z-score for bid-to-cover ratio"""
        try:
            sql = """
            SELECT bid_to_cover
            FROM gov_auction_results
            WHERE date <= ? AND bid_to_cover IS NOT NULL
            ORDER BY date DESC
            LIMIT ?
            """

            result = self.db.con.execute(sql, [target_date.isoformat(), lookback_days]).fetchall()

            if not result or len(result) < 5:
                return None

            btc_values = [row[0] for row in result]

            import statistics
            mean = statistics.mean(btc_values)
            stdev = statistics.stdev(btc_values) if len(btc_values) > 1 else 0

            latest = btc_values[0]

            if stdev > 0:
                return (latest - mean) / stdev
            else:
                return 0.0

        except Exception as e:
            logger.debug(f"Error computing BTC z-score: {e}")
            return None

    def _compute_secondary_zscore(self, target_date: date, lookback_days: int) -> Optional[float]:
        """Compute z-score for secondary trading value"""
        try:
            # Get daily totals
            sql = """
            SELECT date, SUM(value) as daily_total
            FROM gov_secondary_trading
            WHERE date <= ? AND value IS NOT NULL
            GROUP BY date
            ORDER BY date DESC
            LIMIT ?
            """

            result = self.db.con.execute(sql, [target_date.isoformat(), lookback_days]).fetchall()

            if not result or len(result) < 5:
                return None

            values = [row[1] for row in result]

            import statistics
            mean = statistics.mean(values)
            stdev = statistics.stdev(values) if len(values) > 1 else 0

            latest = values[0]

            if stdev > 0:
                return (latest - mean) / stdev
            else:
                return 0.0

        except Exception as e:
            logger.debug(f"Error computing secondary z-score: {e}")
            return None

    def map_bucket(self, score: float) -> str:
        """
        Map transmission score to regime bucket

        B0: Very Easy (0-20)
        B1: Easy (20-40)
        B2: Neutral (40-60)
        B3: Tight (60-80)
        B4: Very Tight (80-100)
        """
        if score <= 20:
            return 'B0'
        elif score <= 40:
            return 'B1'
        elif score <= 60:
            return 'B2'
        elif score <= 80:
            return 'B3'
        else:
            return 'B4'

    def detect_alerts(self, metrics: Dict[str, Any], target_date: Optional[date] = None) -> List[Dict[str, Any]]:
        """
        Detect alerts based on metrics

        Returns:
            List of alert dictionaries
        """
        if target_date is None:
            return []

        from app.analytics.alert_engine import AlertEngine

        def flatten(value: Any) -> Any:
            if isinstance(value, dict):
                if "value" in value:
                    return value.get("value")
                if "value_text" in value:
                    return value.get("value_text")
                return None
            return value

        flat: Dict[str, Any] = {k: flatten(v) for k, v in metrics.items()}

        engine = AlertEngine(self.db)
        return engine.detect_alerts(target_date=target_date, metrics=flat, use_db_thresholds=True)

    def get_top_drivers(self, metrics: Dict[str, Any], top_n: int = 3, n: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get top N drivers contributing to transmission score

        Args:
            score_components: Dictionary of component names to z-scores
            top_n: Number of top drivers to return

        Returns:
            List of driver info with name, contribution, and direction
        """
        n_final = int(n) if n is not None else int(top_n)
        candidates = {k: v for k, v in metrics.items() if k.endswith("_zscore") and isinstance(v, (int, float))}
        if not candidates:
            return []

        sorted_components = sorted(candidates.items(), key=lambda x: abs(x[1]), reverse=True)

        drivers = []
        for name, value in sorted_components[:n_final]:
            direction = "↑" if value > 0 else "↓"
            drivers.append({
                'name': name,
                'contribution': abs(value),
                'direction': direction,
                'value': float(value),
            })

        return drivers
