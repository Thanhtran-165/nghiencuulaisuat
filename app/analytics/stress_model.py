"""
BondY Stress Model - Composite stress index for VN bond market

Computes a 0-100 stress index based on:
- Transmission score (0-100)
- Liquidity z-scores
- Curve slope changes
- Auction weakness signals
- Secondary turnover z-score

Optional global comparators (if FRED data available):
- VN vs US spreads
- Rolling correlation
- Global rate shock alerts
"""
import logging
from datetime import date, timedelta
from typing import Dict, Any, List, Optional, Tuple
import json

logger = logging.getLogger(__name__)


class BondYStressModel:
    """
    BondY Stress Index Model

    Computes composite stress index (0-100) for VN bond market
    with percentile-based normalization and driver decomposition.
    """

    # Stress bucket definitions
    STRESS_BUCKETS = {
        'S0': (0, 20, 'Very Low Stress'),
        'S1': (20, 40, 'Low Stress'),
        'S2': (40, 60, 'Moderate Stress'),
        'S3': (60, 80, 'High Stress'),
        'S4': (80, 100, 'Very High Stress')
    }

    # Component weights
    WEIGHTS = {
        'transmission_score': 0.30,
        'liquidity_stress': 0.25,
        'curve_stress': 0.20,
        'auction_stress': 0.15,
        'turnover_stress': 0.10
    }

    def __init__(self, db_manager):
        """Initialize stress model with database manager"""
        self.db = db_manager

    def compute_stress_index(self, target_date: date) -> Tuple[Optional[float], Optional[str], Dict[str, Any]]:
        """
        Compute BondY stress index for a specific date

        Args:
            target_date: Date to compute stress index for

        Returns:
            Tuple of (stress_index, regime_bucket, components)
        """
        logger.info(f"Computing BondY stress index for {target_date}")

        # Get transmission metrics for target date
        transmission_metrics = self._get_transmission_metrics(target_date)

        if not transmission_metrics:
            logger.warning(f"No transmission metrics available for {target_date}")
            return None, None, {'error': 'No transmission data available'}

        # Get component values
        components = {}
        components['transmission'] = self._get_transmission_component(transmission_metrics)
        components['liquidity'] = self._get_liquidity_stress(target_date)
        components['curve'] = self._get_curve_stress(target_date)
        components['auction'] = self._get_auction_stress(target_date)
        components['turnover'] = self._get_turnover_stress(target_date)

        # Compute percentile ranks for each component
        percentile_ranks = self._compute_percentile_ranks(target_date, components)

        # Calculate composite stress index
        stress_index = self._calculate_composite_score(percentile_ranks)

        if stress_index is None:
            logger.warning("BondY stress index unavailable (insufficient component data)")
            return None, None, {
                'error': 'Insufficient component data to compute stress index',
                'components': components,
                'percentile_ranks': percentile_ranks,
                'drivers': []
            }

        # Map to regime bucket
        regime_bucket = self._map_stress_bucket(stress_index)

        # Get top drivers
        drivers = self._get_top_drivers(percentile_ranks, stress_index)

        result = {
            'stress_index': stress_index,
            'regime_bucket': regime_bucket,
            'components': components,
            'percentile_ranks': percentile_ranks,
            'drivers': drivers,
            'data_availability': {
                'transmission': components['transmission']['value'] is not None,
                'liquidity': components['liquidity']['value'] is not None,
                'curve': components['curve']['value'] is not None,
                'auction': components['auction']['value'] is not None,
                'turnover': components['turnover']['value'] is not None
            }
        }

        logger.info(f"BondY stress index: {stress_index:.1f}/100, bucket: {regime_bucket}")

        return stress_index, regime_bucket, result

    def compute_global_comparators(self, target_date: date) -> Dict[str, Any]:
        """
        Compute VN vs Global comparators

        Args:
            target_date: Date to compute comparators for

        Returns:
            Dictionary with spread metrics and correlations
        """
        logger.info(f"Computing global comparators for {target_date}")

        comparators = {
            'global_available': False,
            'spreads': {},
            'correlations': {},
            'alerts': []
        }

        # Check if global data is available
        global_rates = self.db.get_global_rates(
            start_date=str(target_date - timedelta(days=90)),
            end_date=str(target_date)
        )

        if not global_rates:
            logger.info("No global data available")
            return comparators

        comparators['global_available'] = True

        # Get VN yield curve data
        vn_yields = self._get_vn_yield_history(target_date, days=90)

        if not vn_yields:
            logger.info("No VN yield data available for comparison")
            return comparators

        # Compute spreads
        spreads = self._compute_spreads(target_date, vn_yields, global_rates)
        comparators['spreads'] = spreads

        # Compute rolling correlation
        correlation = self._compute_rolling_correlation(target_date, vn_yields, global_rates)
        comparators['correlations'] = correlation

        # Check for alerts
        alerts = self._check_global_alerts(target_date, vn_yields, global_rates)
        comparators['alerts'] = alerts

        return comparators

    def _get_transmission_metrics(self, target_date: date) -> Optional[Dict[str, Any]]:
        """Get transmission metrics for target date"""
        try:
            metrics = self.db.get_transmission_metrics(
                start_date=str(target_date),
                end_date=str(target_date)
            )

            return {m['metric_name']: m['metric_value'] for m in metrics} if metrics else None
        except Exception as e:
            logger.error(f"Error fetching transmission metrics: {e}")
            return None

    def _get_transmission_component(self, transmission_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Get transmission score component"""
        score = transmission_metrics.get('transmission_score')
        return {
            'value': score,
            'zscore': None,  # Transmission score is already 0-100 normalized
            'weight': self.WEIGHTS['transmission_score']
        }

    def _get_liquidity_stress(self, target_date: date) -> Dict[str, Any]:
        """Get liquidity stress component"""
        try:
            # Get latest interbank rates
            rates = self.db.get_interbank_rates(
                start_date=str(target_date - timedelta(days=60)),
                end_date=str(target_date),
                tenor='ON'
            )

            if not rates:
                return {'value': None, 'zscore': None, 'weight': self.WEIGHTS['liquidity_stress']}

            latest_rate = rates[0]['rate'] if rates else None

            # Compute z-score over 60-day window
            values = [r['rate'] for r in rates]
            zscore = self._compute_zscore(latest_rate, values) if latest_rate and len(values) > 5 else None

            return {
                'value': latest_rate,
                'zscore': zscore,
                'weight': self.WEIGHTS['liquidity_stress']
            }
        except Exception as e:
            logger.error(f"Error computing liquidity stress: {e}")
            return {'value': None, 'zscore': None, 'weight': self.WEIGHTS['liquidity_stress']}

    def _get_curve_stress(self, target_date: date) -> Dict[str, Any]:
        """Get curve slope stress component"""
        try:
            # Get transmission metrics for curve slope
            metrics = self._get_transmission_metrics(target_date)

            if not metrics:
                return {'value': None, 'zscore': None, 'weight': self.WEIGHTS['curve_stress']}

            slope = metrics.get('slope_10y_2y')

            # Get historical slope for z-score
            historical_metrics = self.db.get_transmission_metrics(
                metric_name='slope_10y_2y',
                start_date=str(target_date - timedelta(days=252)),
                end_date=str(target_date)
            )

            if historical_metrics and slope is not None:
                values = [m['metric_value'] for m in historical_metrics if m['metric_value'] is not None]
                zscore = self._compute_zscore(slope, values) if len(values) > 5 else None
            else:
                zscore = None

            return {
                'value': slope,
                'zscore': zscore,
                'weight': self.WEIGHTS['curve_stress']
            }
        except Exception as e:
            logger.error(f"Error computing curve stress: {e}")
            return {'value': None, 'zscore': None, 'weight': self.WEIGHTS['curve_stress']}

    def _get_auction_stress(self, target_date: date) -> Dict[str, Any]:
        """Get auction stress component"""
        try:
            metrics = self._get_transmission_metrics(target_date)

            if not metrics:
                return {'value': None, 'zscore': None, 'weight': self.WEIGHTS['auction_stress']}

            # Use inverse of bid-to-cover as stress indicator
            btc = metrics.get('auction_bid_to_cover_median_20d')

            if btc is None:
                return {'value': None, 'zscore': None, 'weight': self.WEIGHTS['auction_stress']}

            # Lower BTC = higher stress
            stress_value = 2.0 - btc  # Invert: 1.5 BTC -> 0.5 stress

            # Get historical for z-score
            historical_metrics = self.db.get_transmission_metrics(
                metric_name='auction_bid_to_cover_median_20d',
                start_date=str(target_date - timedelta(days=252)),
                end_date=str(target_date)
            )

            if historical_metrics:
                values = [2.0 - m['metric_value'] for m in historical_metrics if m['metric_value'] is not None]
                zscore = self._compute_zscore(stress_value, values) if len(values) > 5 else None
            else:
                zscore = None

            return {
                'value': stress_value,
                'zscore': zscore,
                'weight': self.WEIGHTS['auction_stress']
            }
        except Exception as e:
            logger.error(f"Error computing auction stress: {e}")
            return {'value': None, 'zscore': None, 'weight': self.WEIGHTS['auction_stress']}

    def _get_turnover_stress(self, target_date: date) -> Dict[str, Any]:
        """Get secondary turnover stress component"""
        try:
            metrics = self._get_transmission_metrics(target_date)

            if not metrics:
                return {'value': None, 'zscore': None, 'weight': self.WEIGHTS['turnover_stress']}

            # Use negative z-score of turnover as stress (low turnover = high stress)
            turnover_zscore = metrics.get('secondary_value_zscore_60d')

            stress_value = -turnover_zscore if turnover_zscore is not None else None

            return {
                'value': stress_value,
                'zscore': stress_value,
                'weight': self.WEIGHTS['turnover_stress']
            }
        except Exception as e:
            logger.error(f"Error computing turnover stress: {e}")
            return {'value': None, 'zscore': None, 'weight': self.WEIGHTS['turnover_stress']}

    def _compute_percentile_ranks(self, target_date: date, components: Dict[str, Dict]) -> Dict[str, Optional[float]]:
        """
        Convert component values to percentile ranks over rolling window

        Returns percentile ranks (0-100) for each component
        """
        percentile_ranks = {}

        for component_name, component_data in components.items():
            value = component_data.get('value')
            zscore = component_data.get('zscore')

            # If we have z-score, convert to percentile
            if zscore is not None:
                # Approximate percentile from z-score (using error function)
                import math
                percentile = (1 + math.erf(zscore / math.sqrt(2))) / 2 * 100
                percentile_ranks[component_name] = percentile
            elif value is not None:
                # For transmission score (already 0-100)
                if component_name == 'transmission':
                    percentile_ranks[component_name] = value
                else:
                    # No historical data, can't compute percentile
                    percentile_ranks[component_name] = None
            else:
                percentile_ranks[component_name] = None

        return percentile_ranks

    def _calculate_composite_score(self, percentile_ranks: Dict[str, Optional[float]]) -> Optional[float]:
        """Calculate weighted composite stress score"""
        valid_scores = []
        total_weight = 0.0

        for component_name, percentile in percentile_ranks.items():
            if percentile is not None:
                weight = self.WEIGHTS.get(f'{component_name}_stress', 0) or self.WEIGHTS.get('transmission_score', 0)
                valid_scores.append(percentile * weight)
                total_weight += weight

        if not valid_scores or total_weight == 0:
            return None

        # Normalize by total weight
        composite = sum(valid_scores) / total_weight

        return composite

    def _map_stress_bucket(self, stress_index: Optional[float]) -> Optional[str]:
        """Map stress index to regime bucket"""
        if stress_index is None:
            return None

        for bucket, (lower, upper, _) in self.STRESS_BUCKETS.items():
            if lower <= stress_index <= upper:
                return bucket

        return 'S4' if stress_index > 100 else 'S0'

    def _get_top_drivers(self, percentile_ranks: Dict[str, Optional[float]], current_score: float) -> List[Dict[str, Any]]:
        """Get top N drivers contributing to stress"""
        drivers = []

        component_labels = {
            'transmission': 'Transmission Score',
            'liquidity': 'Liquidity Stress',
            'curve': 'Curve Slope Stress',
            'auction': 'Auction Stress',
            'turnover': 'Turnover Stress'
        }

        for component_name, percentile in percentile_ranks.items():
            if percentile is not None:
                # Contribution is how much this component pushes stress away from neutral (50)
                contribution = (percentile - 50) * self.WEIGHTS.get(f'{component_name}_stress', 0) or self.WEIGHTS.get('transmission_score', 0)

                drivers.append({
                    'name': component_labels.get(component_name, component_name),
                    'value': percentile,
                    'contribution': contribution
                })

        # Sort by absolute contribution
        drivers.sort(key=lambda x: abs(x['contribution']), reverse=True)

        return drivers[:3]

    def _compute_zscore(self, value: float, historical_values: List[float]) -> Optional[float]:
        """Compute z-score for value against historical values"""
        if not historical_values or len(historical_values) < 2:
            return None

        import statistics
        try:
            mean = statistics.mean(historical_values)
            stdev = statistics.stdev(historical_values)

            if stdev == 0:
                return 0.0

            zscore = (value - mean) / stdev

            # Winsorize at ±3
            zscore = max(-3, min(3, zscore))

            return zscore
        except Exception:
            return None

    def _get_vn_yield_history(self, target_date: date, days: int = 90) -> List[Dict[str, Any]]:
        """Get VN yield history"""
        try:
            start_date = target_date - timedelta(days=days)

            sql = """
            SELECT date, tenor_label, spot_rate_annual
            FROM gov_yield_curve
            WHERE date >= ? AND date <= ? AND tenor_label IN ('2Y', '10Y')
            ORDER BY date, tenor_label
            """

            result = self.db.con.execute(sql, [str(start_date), str(target_date)]).fetchall()
            columns = [desc[0] for desc in self.db.con.description]
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Error fetching VN yield history: {e}")
            return []

    def _compute_spreads(self, target_date: date, vn_yields: List[Dict], global_rates: List[Dict]) -> Dict[str, Any]:
        """Compute VN vs Global spreads"""
        spreads = {}

        try:
            # Get latest yields
            vn_10y = next((r['spot_rate_annual'] for r in vn_yields if r['tenor_label'] == '10Y' and r['date'] == target_date), None)
            vn_2y = next((r['spot_rate_annual'] for r in vn_yields if r['tenor_label'] == '2Y' and r['date'] == target_date), None)

            us_10y = next((r['value'] for r in global_rates if r['series_id'] == 'DGS10' and r['date'] == target_date), None)
            us_2y = next((r['value'] for r in global_rates if r['series_id'] == 'DGS2' and r['date'] == target_date), None)

            if vn_10y and us_10y:
                spreads['vn10y_minus_us10y'] = vn_10y - us_10y

            if vn_2y and us_2y:
                spreads['vn2y_minus_us2y'] = vn_2y - us_2y

            if vn_10y and vn_2y and us_10y and us_2y:
                vn_slope = vn_10y - vn_2y
                us_slope = us_10y - us_2y
                spreads['slope_diff'] = vn_slope - us_slope

        except Exception as e:
            logger.error(f"Error computing spreads: {e}")

        return spreads

    def _compute_rolling_correlation(self, target_date: date, vn_yields: List[Dict], global_rates: List[Dict]) -> Dict[str, Any]:
        """Compute 60-day rolling correlation between VN10Y and US10Y"""
        correlations = {}

        try:
            # Get time series for last 60 days
            start_date = target_date - timedelta(days=60)

            vn_series = [r['spot_rate_annual'] for r in vn_yields if r['tenor_label'] == '10Y' and r['date'] >= start_date]
            us_series = [r['value'] for r in global_rates if r['series_id'] == 'DGS10' and r['date'] >= start_date]

            if len(vn_series) > 30 and len(us_series) > 30:
                # Compute correlation
                import statistics
                n = min(len(vn_series), len(us_series))

                if n > 1:
                    vn_mean = statistics.mean(vn_series[-n:])
                    us_mean = statistics.mean(us_series[-n:])

                    covariance = sum((vn_series[-n:][i] - vn_mean) * (us_series[-n:][i] - us_mean) for i in range(n)) / n

                    vn_std = statistics.stdev(vn_series[-n:])
                    us_std = statistics.stdev(us_series[-n:])

                    if vn_std > 0 and us_std > 0:
                        correlation = covariance / (vn_std * us_std)
                        correlations['vn10y_us10y_60d'] = correlation

        except Exception as e:
            logger.error(f"Error computing correlation: {e}")

        return correlations

    def _check_global_alerts(self, target_date: date, vn_yields: List[Dict], global_rates: List[Dict]) -> List[Dict[str, Any]]:
        """Check for global rate shock alerts"""
        alerts = []

        try:
            # Get US10Y 5-day change
            us_10y_history = [r for r in global_rates if r['series_id'] == 'DGS10' and r['date'] >= target_date - timedelta(days=5)]

            if len(us_10y_history) >= 2:
                latest_us = us_10y_history[0]['value']
                earliest_us = us_10y_history[-1]['value']
                us_change = latest_us - earliest_us

                # Check if US10Y moved significantly (> 0.25%)
                if abs(us_change) > 0.25:
                    # Check if VN stress is also rising
                    stress_history = self.db.get_bondy_stress(
                        start_date=str(target_date - timedelta(days=5)),
                        end_date=str(target_date)
                    )

                    if stress_history and len(stress_history) >= 2:
                        latest_stress = stress_history[0]['stress_index']
                        earliest_stress = stress_history[-1]['stress_index']

                        if latest_stress and earliest_stress and latest_stress > earliest_stress:
                            alerts.append({
                                'alert_type': 'ALERT_GLOBAL_RATE_SHOCK',
                                'severity': 'HIGH' if us_change > 0.25 else 'MEDIUM',
                                'message': f"US10Y {'rose' if us_change > 0 else 'fell'} {abs(us_change):.2f}% in 5 days while VN stress rising",
                                'metric_value': us_change,
                                'threshold': 0.25
                            })

            # Check for spread widening
            spread_history = self._compute_spreads(target_date, vn_yields, global_rates)

            if 'vn10y_minus_us10y' in spread_history:
                current_spread = spread_history['vn10y_minus_us10y']

                # Get spread 5 days ago
                past_date = target_date - timedelta(days=5)
                past_vn_yields = self._get_vn_yield_history(past_date, days=10)
                past_spreads = self._compute_spreads(past_date, past_vn_yields, global_rates)

                if 'vn10y_minus_us10y' in past_spreads:
                    past_spread = past_spreads['vn10y_minus_us10y']
                    spread_change = current_spread - past_spread

                    if spread_change > 0.5:  # Spread widened by > 0.5%
                        alerts.append({
                            'alert_type': 'ALERT_SPREAD_WIDENING',
                            'severity': 'HIGH' if spread_change > 1.0 else 'MEDIUM',
                            'message': f"VN-US spread widened by {spread_change:.2f}% over 5 days",
                            'metric_value': spread_change,
                            'threshold': 0.5
                        })

        except Exception as e:
            logger.error(f"Error checking global alerts: {e}")

        return alerts
