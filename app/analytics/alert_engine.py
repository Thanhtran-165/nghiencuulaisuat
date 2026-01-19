"""
Threshold-based Alert Engine

Loads alert thresholds from database and performs alert detection.
Allows users to customize alert sensitivity without code changes.
"""
import logging
from datetime import date
from typing import Dict, Any, List, Optional
import statistics

logger = logging.getLogger(__name__)


class AlertEngine:
    """Alert detection using configurable thresholds from database"""

    def __init__(self, db_manager):
        """
        Initialize alert engine

        Args:
            db_manager: Database manager instance
        """
        self.db = db_manager
        self._threshold_cache = None
        self._cache_timestamp = None

    def _load_thresholds(self, force_reload: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        Load alert thresholds from database

        Args:
            force_reload: Force reload from database even if cached

        Returns:
            Dictionary mapping alert_code to threshold config
        """
        # Check cache (5 minute TTL)
        import time
        if not force_reload and self._threshold_cache:
            if self._cache_timestamp and (time.time() - self._cache_timestamp) < 300:
                return self._threshold_cache

        try:
            # Query thresholds from database
            sql = """
            SELECT alert_code, enabled, severity, params_json
            FROM alert_thresholds
            """

            results = self.db.con.execute(sql).fetchall()

            thresholds = {}
            for row in results:
                alert_code, enabled, severity, params_json = row
                if enabled:
                    import json
                    params = json.loads(params_json) if params_json else {}
                    thresholds[alert_code] = {
                        'severity': severity,
                        'params': params
                    }

            # Update cache
            self._threshold_cache = thresholds
            self._cache_timestamp = time.time()

            logger.info(f"Loaded {len(thresholds)} alert thresholds from database")
            return thresholds

        except Exception as e:
            logger.error(f"Error loading thresholds from database: {e}")
            # Return empty dict - will use default behavior
            return {}

    def detect_alerts(
        self,
        target_date: date,
        metrics: Dict[str, Any],
        use_db_thresholds: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Detect alerts based on metrics and thresholds

        Args:
            target_date: Date to detect alerts for
            metrics: Computed metrics dictionary
            use_db_thresholds: If True, load thresholds from DB; if False, use hardcoded defaults

        Returns:
            List of alert dictionaries
        """
        alerts = []

        if use_db_thresholds:
            thresholds = self._load_thresholds()
            # Backwards-compatible default: if the DB has no rows (fresh install),
            # fall back to hardcoded thresholds so alerting still works.
            if not thresholds:
                thresholds = self._get_default_thresholds()
        else:
            thresholds = self._get_default_thresholds()

        # ALERT_TRANSMISSION_TIGHTENING (adaptive, z-score over recent history)
        if 'ALERT_TRANSMISSION_TIGHTENING' in thresholds:
            alert = self._check_transmission_tightening(target_date, metrics, thresholds['ALERT_TRANSMISSION_TIGHTENING'])
            if alert:
                alerts.append(alert)

        # ALERT_TRANSMISSION_JUMP (absolute daily jump in score)
        if 'ALERT_TRANSMISSION_JUMP' in thresholds:
            alert = self._check_transmission_jump(target_date, metrics, thresholds['ALERT_TRANSMISSION_JUMP'])
            if alert:
                alerts.append(alert)

        # ALERT_LIQUIDITY_SPIKE
        if 'ALERT_LIQUIDITY_SPIKE' in thresholds:
            alert = self._check_liquidity_spike(metrics, thresholds['ALERT_LIQUIDITY_SPIKE'])
            if alert:
                alerts.append(alert)

        # ALERT_CURVE_BEAR_STEEPEN
        if 'ALERT_CURVE_BEAR_STEEPEN' in thresholds:
            alert = self._check_curve_bear_steepen(metrics, thresholds['ALERT_CURVE_BEAR_STEEPEN'])
            if alert:
                alerts.append(alert)

        # ALERT_AUCTION_WEAK
        if 'ALERT_AUCTION_WEAK' in thresholds:
            alert = self._check_auction_weak(metrics, thresholds['ALERT_AUCTION_WEAK'])
            if alert:
                alerts.append(alert)

        # ALERT_TURNOVER_DROP
        if 'ALERT_TURNOVER_DROP' in thresholds:
            alert = self._check_turnover_drop(metrics, thresholds['ALERT_TURNOVER_DROP'])
            if alert:
                alerts.append(alert)

        # ALERT_POLICY_CHANGE
        if 'ALERT_POLICY_CHANGE' in thresholds:
            alert = self._check_policy_change(metrics, thresholds['ALERT_POLICY_CHANGE'])
            if alert:
                alerts.append(alert)

        # ALERT_TRANSMISSION_HIGH (new)
        if 'ALERT_TRANSMISSION_HIGH' in thresholds:
            alert = self._check_transmission_high(metrics, thresholds['ALERT_TRANSMISSION_HIGH'])
            if alert:
                alerts.append(alert)

        # ALERT_STRESS_HIGH (new)
        if 'ALERT_STRESS_HIGH' in thresholds:
            alert = self._check_stress_high(metrics, thresholds['ALERT_STRESS_HIGH'])
            if alert:
                alerts.append(alert)

        return alerts

    def _build_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        metric_value: Optional[float] = None,
        threshold: Optional[float] = None,
        source_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "alert_type": alert_type,
            "alert_code": alert_type,
            "severity": severity,
            "message": message,
            "metric_value": metric_value,
            "threshold": threshold,
            "source_data": source_data or {},
        }

    def _check_transmission_tightening(self, target_date: date, metrics: Dict, config: Dict) -> Optional[Dict]:
        """
        Detect unusually "tight" conditions using z-score over recent history.
        Uses train-only history (date < target_date) to avoid leakage.
        """
        params = config.get("params", {})
        lookback = int(params.get("lookback", 120))
        min_n = int(params.get("min_n", 30))
        z_low = float(params.get("z_low", 1.0))
        z_medium = float(params.get("z_medium", 1.3))
        z_high = float(params.get("z_high", 2.0))

        score = metrics.get("transmission_score")
        if not isinstance(score, (int, float)):
            return None

        rows = self.db.con.execute(
            """
            SELECT metric_value
            FROM transmission_daily_metrics
            WHERE metric_name = 'transmission_score'
              AND date < ?
              AND metric_value IS NOT NULL
            ORDER BY date DESC
            LIMIT ?
            """,
            [target_date.isoformat(), lookback],
        ).fetchall()
        hist = [float(r[0]) for r in rows if r and isinstance(r[0], (int, float))]
        if len(hist) < min_n:
            return None

        mean = statistics.mean(hist)
        stdev = statistics.stdev(hist) if len(hist) > 1 else 0.0
        z = (float(score) - mean) / stdev if stdev > 0 else 0.0

        severity = None
        z_trigger = None
        if z >= z_high:
            severity = "HIGH"
            z_trigger = z_high
        elif z >= z_medium:
            severity = "MEDIUM"
            z_trigger = z_medium
        elif z >= z_low:
            severity = "LOW"
            z_trigger = z_low

        if not severity:
            return None

        threshold_score = float(mean + (float(z_trigger) * stdev)) if stdev > 0 else None
        return self._build_alert(
            "ALERT_TRANSMISSION_TIGHTENING",
            severity,
            f"Transmission tightening (z={z:.2f} vs {len(hist)} obs)",
            metric_value=float(score),
            threshold=threshold_score,
            source_data={
                "z": float(z),
                "lookback": lookback,
                "n": len(hist),
                "mean": float(mean),
                "stdev": float(stdev),
                "z_thresholds": {"low": z_low, "medium": z_medium, "high": z_high},
                "evidence": {
                    "metric": "transmission_score",
                    "unit": "points",
                    "method": "zscore_over_history",
                    "history_end_exclusive": True,
                    "lookback": lookback,
                    "min_n": min_n,
                    "n": len(hist),
                    "mean": float(mean),
                    "stdev": float(stdev),
                    "z": float(z),
                    "z_trigger": float(z_trigger) if z_trigger is not None else None,
                    "threshold_score": threshold_score,
                },
            },
        )

    def _check_transmission_jump(self, target_date: date, metrics: Dict, config: Dict) -> Optional[Dict]:
        """
        Detect large day-to-day jumps in transmission_score.
        """
        params = config.get("params", {})
        jump_medium = float(params.get("jump_medium", 7.0))
        jump_high = float(params.get("jump_high", 12.0))

        score = metrics.get("transmission_score")
        if not isinstance(score, (int, float)):
            return None

        prev = self.db.con.execute(
            """
            SELECT date, metric_value
            FROM transmission_daily_metrics
            WHERE metric_name = 'transmission_score'
              AND date < ?
              AND metric_value IS NOT NULL
            ORDER BY date DESC
            LIMIT 1
            """,
            [target_date.isoformat()],
        ).fetchone()
        if not prev or len(prev) < 2 or not isinstance(prev[1], (int, float)):
            return None

        prev_date = prev[0]
        prev_value = float(prev[1])
        delta = float(score) - prev_value
        abs_delta = abs(delta)
        if abs_delta >= jump_high:
            severity = "HIGH"
            threshold = jump_high
        elif abs_delta >= jump_medium:
            severity = "MEDIUM"
            threshold = jump_medium
        else:
            return None

        return self._build_alert(
            "ALERT_TRANSMISSION_JUMP",
            severity,
            f"Transmission score jump ({delta:+.1f} pts)",
            metric_value=float(delta),
            threshold=float(threshold),
            source_data={
                "today": float(score),
                "prev": prev_value,
                "prev_date": str(prev_date) if prev_date is not None else None,
                "delta": float(delta),
                "evidence": {
                    "metric": "transmission_score",
                    "unit": "points",
                    "method": "absolute_delta_vs_previous_available",
                    "baseline_date": str(prev_date) if prev_date is not None else None,
                    "baseline_value": prev_value,
                    "current_value": float(score),
                    "delta": float(delta),
                    "threshold_abs": float(threshold),
                },
            },
        )

    def _check_liquidity_spike(self, metrics: Dict, config: Dict) -> Optional[Dict]:
        """Check for liquidity spike alert"""
        params = config.get('params', {})
        z_min = params.get('z_min', 2.0)
        on_min = params.get('on_min', 2.0)

        zscore_raw = metrics.get('ib_on_zscore_20d')
        zscore = float(zscore_raw) if isinstance(zscore_raw, (int, float)) else None
        ib_on_raw = metrics.get('ib_on')
        ib_on = float(ib_on_raw) if isinstance(ib_on_raw, (int, float)) else None

        triggered = False
        trigger_mode = None
        threshold = None

        # Prefer z-score trigger when available.
        if zscore is not None and zscore >= float(z_min):
            triggered = True
            trigger_mode = "zscore"
            threshold = float(z_min)

        # Absolute fallback trigger (in percent points). This can be noisy if on_min is too low.
        if ib_on is not None and ib_on >= float(on_min):
            triggered = True
            trigger_mode = trigger_mode or "absolute"
            threshold = float(on_min) if threshold is None else threshold

        if triggered:
            # Normalize how we expose values in UI:
            # - If triggered by z-score, metric_value/threshold are z units.
            # - If triggered by absolute, metric_value/threshold are percent units.
            if trigger_mode == "zscore":
                metric_value = float(zscore) if zscore is not None else None
                threshold_value = float(z_min)
                message = f"Interbank ON spike (z={metric_value:.2f} ≥ {threshold_value:.2f})"
            else:
                metric_value = float(ib_on) if ib_on is not None else None
                threshold_value = float(on_min)
                message = f"Interbank ON high ({metric_value:.2f}% ≥ {threshold_value:.2f}%)" if metric_value is not None else "Interbank ON high"

            return self._build_alert(
                'ALERT_LIQUIDITY_SPIKE',
                config.get('severity', 'HIGH'),
                message,
                metric_value=metric_value,
                threshold=threshold_value,
                source_data={
                    'ib_on': ib_on,
                    'ib_on_zscore_20d': zscore,
                    'ib_effective_date': metrics.get('ib_effective_date'),
                    'thresholds': {'z_min': z_min, 'on_min': on_min},
                    'trigger_mode': trigger_mode,
                    'evidence': {
                        'metric': 'ib_on' if trigger_mode != 'zscore' else 'ib_on_zscore_20d',
                        'unit': '%' if trigger_mode != 'zscore' else 'z',
                        'method': 'threshold',
                        'trigger_mode': trigger_mode,
                        'current_value': metric_value,
                        'threshold': threshold_value,
                        'effective_date': metrics.get('ib_effective_date'),
                    },
                }
            )
        return None

    def _check_curve_bear_steepen(self, metrics: Dict, config: Dict) -> Optional[Dict]:
        """Check for bear steepening alert"""
        params = config.get('params', {})
        bps_change_20d_min = params.get('bps_change_20d_min', 20)  # bps
        slope_min = params.get('slope_min', 2.0)  # absolute level

        # Check either absolute level or recent change
        slope_raw = metrics.get('slope_10y_2y')
        slope = float(slope_raw) if isinstance(slope_raw, (int, float)) else None
        slope_change_raw = metrics.get('slope_10y_2y_change_20d')
        slope_change_20d = float(slope_change_raw) if isinstance(slope_change_raw, (int, float)) else None

        triggered = False
        trigger_mode = None
        threshold = None
        if slope is not None and slope >= slope_min:
            triggered = True
            trigger_mode = "absolute"
            threshold = float(slope_min)
        if slope_change_20d is not None and slope_change_20d >= (bps_change_20d_min / 100):
            triggered = True
            trigger_mode = trigger_mode or "change"
            threshold = threshold if threshold is not None else float(bps_change_20d_min / 100)

        if triggered:
            return self._build_alert(
                'ALERT_CURVE_BEAR_STEEPEN',
                config.get('severity', 'MEDIUM'),
                f"Yield curve steepening (10Y-2Y slope: {slope:.2f}%)" if slope is not None else "Yield curve steepening",
                metric_value=float(slope) if slope is not None else None,
                threshold=threshold,
                source_data={
                    'slope_10y_2y': slope,
                    'slope_10y_2y_change_20d': slope_change_20d,
                    'thresholds': {'slope_min': slope_min, 'bps_change_20d_min': bps_change_20d_min},
                    'trigger_mode': trigger_mode,
                    'evidence': {
                        'metric': 'slope_10y_2y' if trigger_mode == 'absolute' else 'slope_10y_2y_change_20d',
                        'unit': '%',
                        'method': 'threshold',
                        'trigger_mode': trigger_mode,
                        'current_value': slope if trigger_mode == 'absolute' else slope_change_20d,
                        'threshold': float(threshold) if threshold is not None else None,
                    },
                }
            )
        return None

    def _check_auction_weak(self, metrics: Dict, config: Dict) -> Optional[Dict]:
        """Check for weak auction alert"""
        params = config.get('params', {})
        btc_max = params.get('btc_max', 1.2)

        btc_raw = metrics.get('auction_bid_to_cover_median_20d')
        btc = float(btc_raw) if isinstance(btc_raw, (int, float)) else None
        if btc is not None and btc < btc_max:
            return self._build_alert(
                'ALERT_AUCTION_WEAK',
                config.get('severity', 'MEDIUM'),
                f"Weak auction demand (BTC: {btc:.2f})",
                metric_value=float(btc),
                threshold=float(btc_max),
                source_data={
                    'auction_bid_to_cover_median_20d': btc,
                    'btc_max': btc_max,
                    'evidence': {
                        'metric': 'auction_bid_to_cover_median_20d',
                        'unit': 'ratio',
                        'method': 'threshold',
                        'current_value': float(btc),
                        'threshold': float(btc_max),
                        'direction': 'below_is_worse',
                    },
                }
            )
        return None

    def _check_turnover_drop(self, metrics: Dict, config: Dict) -> Optional[Dict]:
        """Check for turnover drop alert"""
        params = config.get('params', {})
        z_max = params.get('z_max', params.get('zscore_max', -1.5))

        zscore_raw = metrics.get('secondary_value_zscore_60d')
        zscore = float(zscore_raw) if isinstance(zscore_raw, (int, float)) else None
        if zscore is not None and zscore <= z_max:
            return self._build_alert(
                'ALERT_TURNOVER_DROP',
                config.get('severity', 'MEDIUM'),
                f"Secondary market turnover drop (z-score: {zscore:.2f})",
                metric_value=float(zscore),
                threshold=float(z_max),
                source_data={
                    'secondary_value_zscore_60d': zscore,
                    'z_max': z_max,
                    'evidence': {
                        'metric': 'secondary_value_zscore_60d',
                        'unit': 'z',
                        'method': 'threshold',
                        'current_value': float(zscore),
                        'threshold': float(z_max),
                        'direction': 'below_is_worse',
                    },
                }
            )
        return None

    def _check_policy_change(self, metrics: Dict, config: Dict) -> Optional[Dict]:
        """Check for policy change alert"""
        if metrics.get('policy_change_flag', False):
            return self._build_alert(
                'ALERT_POLICY_CHANGE',
                config.get('severity', 'HIGH'),
                "Policy rate change detected",
                metric_value=None,
                threshold=None,
                source_data={
                    'refinancing': metrics.get('policy_refinancing'),
                    'rediscount': metrics.get('policy_rediscount'),
                    'base': metrics.get('policy_base'),
                    'evidence': {
                        'metric': 'policy_rates',
                        'unit': '%',
                        'method': 'change_flag',
                        'refinancing': metrics.get('policy_refinancing'),
                        'rediscount': metrics.get('policy_rediscount'),
                        'base': metrics.get('policy_base'),
                    },
                }
            )
        return None

    def _check_transmission_high(self, metrics: Dict, config: Dict) -> Optional[Dict]:
        """Check for high transmission score alert"""
        params = config.get('params', {})
        score_min = params.get('score_min', 60)

        score_raw = metrics.get('transmission_score')
        score = float(score_raw) if isinstance(score_raw, (int, float)) else None
        if score is not None and score >= score_min:
            return self._build_alert(
                'ALERT_TRANSMISSION_HIGH',
                config.get('severity', 'MEDIUM'),
                f"High transmission score ({score:.1f}/100)",
                metric_value=float(score),
                threshold=float(score_min),
                source_data={
                    'transmission_score': score,
                    'score_min': score_min,
                    'evidence': {
                        'metric': 'transmission_score',
                        'unit': 'points',
                        'method': 'absolute_threshold',
                        'current_value': float(score),
                        'threshold': float(score_min),
                    },
                }
            )
        return None

    def _check_stress_high(self, metrics: Dict, config: Dict) -> Optional[Dict]:
        """Check for high stress index alert"""
        params = config.get('params', {})
        stress_min = params.get('stress_min', 60)

        stress_raw = metrics.get('stress_index')
        stress = float(stress_raw) if isinstance(stress_raw, (int, float)) else None
        if stress is not None and stress >= stress_min:
            return self._build_alert(
                'ALERT_STRESS_HIGH',
                config.get('severity', 'HIGH'),
                f"High BondY stress index ({stress:.1f}/100)",
                metric_value=float(stress),
                threshold=float(stress_min),
                source_data={
                    'stress_index': stress,
                    'stress_min': stress_min,
                    'evidence': {
                        'metric': 'stress_index',
                        'unit': 'points',
                        'method': 'absolute_threshold',
                        'current_value': float(stress),
                        'threshold': float(stress_min),
                    },
                }
            )
        return None

    def _get_default_thresholds(self) -> Dict[str, Dict]:
        """Get default hardcoded thresholds (fallback)"""
        return {
            'ALERT_TRANSMISSION_TIGHTENING': {
                'severity': 'MEDIUM',
                'params': {'lookback': 120, 'min_n': 30, 'z_low': 1.0, 'z_medium': 1.3, 'z_high': 2.0}
            },
            'ALERT_TRANSMISSION_JUMP': {
                'severity': 'MEDIUM',
                'params': {'jump_medium': 7.0, 'jump_high': 12.0}
            },
            'ALERT_LIQUIDITY_SPIKE': {
                'severity': 'HIGH',
                'params': {'z_min': 2.0, 'on_min': 2.0}
            },
            'ALERT_CURVE_BEAR_STEEPEN': {
                'severity': 'MEDIUM',
                'params': {'bps_change_20d_min': 20, 'slope_min': 2.0}
            },
            'ALERT_AUCTION_WEAK': {
                'severity': 'MEDIUM',
                'params': {'btc_max': 1.2}
            },
            'ALERT_TURNOVER_DROP': {
                'severity': 'MEDIUM',
                'params': {'z_max': -1.5}
            },
            'ALERT_POLICY_CHANGE': {
                'severity': 'HIGH',
                'params': {}
            },
            'ALERT_TRANSMISSION_HIGH': {
                'severity': 'MEDIUM',
                'params': {'score_min': 60}
            },
            'ALERT_STRESS_HIGH': {
                'severity': 'HIGH',
                'params': {'stress_min': 60}
            }
        }

    def test_threshold(
        self,
        alert_code: str,
        metrics: Dict[str, Any],
        custom_params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Test a specific alert threshold with given metrics

        Args:
            alert_code: Alert code to test
            metrics: Metrics to test against
            custom_params: Optional custom parameters (overrides DB)

        Returns:
            Dictionary with test results
        """
        thresholds = self._load_thresholds()

        if alert_code not in thresholds:
            return {
                'alert_code': alert_code,
                'triggered': False,
                'error': 'Alert code not found in thresholds'
            }

        config = thresholds[alert_code]

        # Override with custom params if provided
        if custom_params:
            config = {
                'severity': config['severity'],
                'params': {**config.get('params', {}), **custom_params}
            }

        # Dispatch to appropriate check method
        check_methods = {
            'ALERT_TRANSMISSION_TIGHTENING': lambda m, c: self._check_transmission_tightening(date.today(), m, c),
            'ALERT_TRANSMISSION_JUMP': lambda m, c: self._check_transmission_jump(date.today(), m, c),
            'ALERT_LIQUIDITY_SPIKE': self._check_liquidity_spike,
            'ALERT_CURVE_BEAR_STEEPEN': self._check_curve_bear_steepen,
            'ALERT_AUCTION_WEAK': self._check_auction_weak,
            'ALERT_TURNOVER_DROP': self._check_turnover_drop,
            'ALERT_POLICY_CHANGE': self._check_policy_change,
            'ALERT_TRANSMISSION_HIGH': self._check_transmission_high,
            'ALERT_STRESS_HIGH': self._check_stress_high
        }

        check_func = check_methods.get(alert_code)
        if not check_func:
            return {
                'alert_code': alert_code,
                'triggered': False,
                'error': 'No check method implemented'
            }

        alert = check_func(metrics, config)

        return {
            'alert_code': alert_code,
            'triggered': alert is not None,
            'config': config,
            'alert': alert if alert else None
        }
