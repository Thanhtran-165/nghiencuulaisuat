"""
Baseline utilities for "So với hôm qua" comparisons

Finds the most recent prior date with available analytics data,
handling weekends, holidays, and missing data gracefully.
"""
import logging
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def get_latest_available_date(db_manager, target_date: date) -> Optional[date]:
    """
    Get the latest date with analytics data on or before target_date

    Args:
        db_manager: Database manager instance
        target_date: Date to search for

    Returns:
        Latest date with data <= target_date, or None if no data exists
    """
    try:
        # Prefer bondy_stress_daily as it's the most comprehensive
        sql = """
        SELECT MAX(date) as latest_date
        FROM bondy_stress_daily
        WHERE date <= ? AND stress_index IS NOT NULL
        """

        result = db_manager.con.execute(sql, [str(target_date)]).fetchone()

        if result and result[0]:
            return result[0]

        # Fallback to transmission_daily_metrics
        sql = """
        SELECT MAX(date) as latest_date
        FROM transmission_daily_metrics
        WHERE date <= ? AND metric_name = 'transmission_score' AND metric_value IS NOT NULL
        """

        result = db_manager.con.execute(sql, [str(target_date)]).fetchone()

        if result and result[0]:
            return result[0]

        return None

    except Exception as e:
        logger.error(f"Error getting latest available date: {e}")
        return None


def get_previous_available_date(db_manager, target_date: date) -> Optional[date]:
    """
    Get the most recent prior date with analytics data (strictly before target_date)

    Args:
        db_manager: Database manager instance
        target_date: Date to search backwards from

    Returns:
        Latest date with data < target_date, or None if no prior data exists
    """
    try:
        # Look for any date before target_date
        sql = """
        SELECT MAX(date) as previous_date
        FROM bondy_stress_daily
        WHERE date < ? AND stress_index IS NOT NULL
        """

        result = db_manager.con.execute(sql, [str(target_date)]).fetchone()

        if result and result[0]:
            return result[0]

        # Fallback to transmission_daily_metrics
        sql = """
        SELECT MAX(date) as previous_date
        FROM transmission_daily_metrics
        WHERE date < ? AND metric_name = 'transmission_score' AND metric_value IS NOT NULL
        """

        result = db_manager.con.execute(sql, [str(target_date)]).fetchone()

        if result and result[0]:
            return result[0]

        return None

    except Exception as e:
        logger.error(f"Error getting previous available date: {e}")
        return None


def get_baseline_data(db_manager, baseline_date: date) -> dict:
    """
    Get all analytics data for a specific baseline date

    Args:
        db_manager: Database manager instance
        baseline_date: Date to fetch data for

    Returns:
        Dictionary with transmission metrics and stress data
    """
    try:
        # Get transmission metrics
        trans_metrics = db_manager.get_transmission_metrics(
            start_date=str(baseline_date),
            end_date=str(baseline_date)
        )

        transmission_dict = {m['metric_name']: m['metric_value'] for m in trans_metrics} if trans_metrics else {}

        # Get stress data
        stress_data = db_manager.get_bondy_stress(
            start_date=str(baseline_date),
            end_date=str(baseline_date)
        )

        stress_dict = stress_data[0] if stress_data else {}

        return {
            'transmission': transmission_dict,
            'stress': stress_dict,
            'date': baseline_date
        }

    except Exception as e:
        logger.error(f"Error getting baseline data: {e}")
        return {
            'transmission': {},
            'stress': {},
            'date': baseline_date
        }


def compute_deltas(current_data: dict, baseline_data: dict) -> dict:
    """
    Compute deltas between current and baseline data

    Args:
        current_data: Current date's data
        baseline_data: Baseline date's data

    Returns:
        Dictionary with computed deltas
    """
    deltas = {}

    # Transmission score delta
    curr_score = current_data.get('transmission', {}).get('transmission_score')
    base_score = baseline_data.get('transmission', {}).get('transmission_score')

    if curr_score is not None and base_score is not None:
        deltas['transmission_score'] = {
            'current': curr_score,
            'baseline': base_score,
            'change': curr_score - base_score
        }

    # Stress index delta
    curr_stress = current_data.get('stress', {}).get('stress_index')
    base_stress = baseline_data.get('stress', {}).get('stress_index')

    if curr_stress is not None and base_stress is not None:
        deltas['stress_index'] = {
            'current': curr_stress,
            'baseline': base_stress,
            'change': curr_stress - base_stress
        }

    # 10Y yield delta
    curr_10y = current_data.get('transmission', {}).get('level_10y')
    base_10y = baseline_data.get('transmission', {}).get('level_10y')

    if curr_10y is not None and base_10y is not None:
        deltas['level_10y'] = {
            'current': curr_10y,
            'baseline': base_10y,
            'change': curr_10y - base_10y
        }

    # Interbank ON delta
    curr_ib = current_data.get('transmission', {}).get('ib_on')
    base_ib = baseline_data.get('transmission', {}).get('ib_on')

    if curr_ib is not None and base_ib is not None:
        deltas['ib_on'] = {
            'current': curr_ib,
            'baseline': base_ib,
            'change': curr_ib - base_ib
        }

    return deltas
