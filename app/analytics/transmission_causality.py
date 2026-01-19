"""
Transmission Causality & Lead-Lag Analytics

Design goal:
- Provide a full research-oriented toolkit (lead-lag, Granger, VAR/IRF) while
  gracefully degrading when data or optional dependencies are missing.
- IB/Policy series automatically "turn on" when enough history exists.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SeriesInfo:
    id: str
    label: str
    unit: str
    min_obs_recommended: int


SERIES_CATALOG: list[SeriesInfo] = [
    SeriesInfo("yield_10y", "VN 10Y Yield", "%", 60),
    SeriesInfo("yield_2y", "VN 2Y Yield", "%", 60),
    SeriesInfo("slope_10y_2y", "VN Curve Slope (10Y-2Y)", "%", 60),
    SeriesInfo("auction_btc", "Auction Bid-to-Cover (median)", "x", 40),
    SeriesInfo("auction_sold", "Auction Amount Sold (total)", "VND", 40),
    SeriesInfo("secondary_value", "Secondary Trading Value (total)", "VND", 60),
    SeriesInfo("bank_deposit_avg_12m", "Bank Deposit Avg (12M, best-per-bank)", "%", 30),
    SeriesInfo("bank_loan_avg", "Bank Loan Avg (best-per-bank)", "%", 30),
    SeriesInfo("ib_on", "Interbank ON", "%", 20),
    SeriesInfo("policy_anchor", "Policy Anchor (Refi/Base/Rediscount)", "%", 20),
    SeriesInfo("us10y", "US 10Y (FRED DGS10)", "%", 60),
    SeriesInfo("spread_vn10y_us10y", "VN10Y - US10Y Spread", "pp", 60),
    SeriesInfo("transmission_score", "Transmission Score (0-100)", "score", 60),
    SeriesInfo("stress_index", "BondY Stress Index (0-100)", "score", 60),
]


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _pearson_corr(x: list[float], y: list[float]) -> Optional[float]:
    if len(x) != len(y) or len(x) < 5:
        return None
    mx = sum(x) / len(x)
    my = sum(y) / len(y)
    sx = math.sqrt(sum((v - mx) ** 2 for v in x))
    sy = math.sqrt(sum((v - my) ** 2 for v in y))
    if sx <= 0 or sy <= 0:
        return None
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return float(cov / (sx * sy))


def _normal_cdf(x: float) -> float:
    # Standard normal CDF using error function (no scipy dependency).
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _corr_inference(r: float, n_pairs: int, m_tests: int) -> dict[str, Optional[float]]:
    """
    Inference for Pearson correlation via Fisher z-transform.

    Returns:
      - p_value (two-sided, H0: rho=0)
      - p_value_adj (Bonferroni, m_tests)
      - ci95_low / ci95_high (95% CI on rho)
    """
    if n_pairs < 6:
        return {"p_value": None, "p_value_adj": None, "ci95_low": None, "ci95_high": None}

    # Clip for numerical stability.
    r_clipped = max(-0.999999, min(0.999999, float(r)))
    z = math.atanh(r_clipped)
    se = 1.0 / math.sqrt(n_pairs - 3.0)
    if se <= 0:
        return {"p_value": None, "p_value_adj": None, "ci95_low": None, "ci95_high": None}

    z_stat = abs(z) / se
    p = 2.0 * (1.0 - _normal_cdf(z_stat))
    if not (0.0 <= p <= 1.0):
        p = None

    z_crit = 1.96
    ci_low = math.tanh(z - z_crit * se)
    ci_high = math.tanh(z + z_crit * se)

    p_adj = None
    if p is not None and m_tests > 0:
        p_adj = min(1.0, p * float(m_tests))

    return {
        "p_value": float(p) if p is not None else None,
        "p_value_adj": float(p_adj) if p_adj is not None else None,
        "ci95_low": float(ci_low),
        "ci95_high": float(ci_high),
    }


class TransmissionCausality:
    def __init__(self, db_manager):
        self.db = db_manager

    def list_series(self) -> list[dict[str, Any]]:
        return [
            {
                "id": s.id,
                "label": s.label,
                "unit": s.unit,
                "min_obs_recommended": s.min_obs_recommended,
            }
            for s in SERIES_CATALOG
        ]

    def get_series(
        self,
        series_id: str,
        start_date: date,
        end_date: date,
    ) -> list[tuple[date, float]]:
        if series_id == "yield_10y":
            return self._yield_by_tenor("10Y", start_date, end_date)
        if series_id == "yield_2y":
            return self._yield_by_tenor("2Y", start_date, end_date)
        if series_id == "slope_10y_2y":
            return self._curve_slope_10y_2y(start_date, end_date)
        if series_id == "auction_btc":
            return self._auction_btc(start_date, end_date)
        if series_id == "auction_sold":
            return self._auction_sold(start_date, end_date)
        if series_id == "secondary_value":
            return self._secondary_value(start_date, end_date)
        if series_id == "bank_deposit_avg_12m":
            return self._bank_deposit_avg(term_months=12, start_date=start_date, end_date=end_date)
        if series_id == "bank_loan_avg":
            return self._bank_loan_avg(start_date=start_date, end_date=end_date)
        if series_id == "ib_on":
            return self._interbank("ON", start_date, end_date)
        if series_id == "policy_anchor":
            return self._policy_anchor_ffill(start_date, end_date)
        if series_id == "us10y":
            return self._global("DGS10", start_date, end_date)
        if series_id == "spread_vn10y_us10y":
            vn = self._yield_by_tenor("10Y", start_date, end_date)
            us = self._global("DGS10", start_date, end_date)
            vn_map = {d: v for d, v in vn}
            us_map = {d: v for d, v in us}
            dates = sorted(set(vn_map.keys()) & set(us_map.keys()))
            return [(d, float(vn_map[d]) - float(us_map[d])) for d in dates]
        if series_id == "transmission_score":
            return self._transmission_metric("transmission_score", start_date, end_date)
        if series_id == "stress_index":
            return self._stress_index(start_date, end_date)

        raise ValueError(f"Unknown series_id: {series_id}")

    def _bank_deposit_avg(self, term_months: int, start_date: date, end_date: date) -> list[tuple[date, float]]:
        max_pr = int(getattr(settings, "lai_suat_max_source_priority", 1))
        rows = self.db.con.execute(
            """
            WITH per_bank AS (
              SELECT date, bank_name, MAX(rate_pct) AS best_rate
              FROM bank_rates
              WHERE product_group = 'deposit'
                AND term_months = ?
                AND rate_pct IS NOT NULL
                AND ((source_priority IS NULL OR source_priority <= ?) OR (source_url IS NOT NULL AND source_url LIKE ?))
                AND date >= ? AND date <= ?
              GROUP BY date, bank_name
            )
            SELECT date, AVG(best_rate) AS v
            FROM per_bank
            GROUP BY date
            ORDER BY date
            """,
            [int(term_months), int(max_pr), "%timo.vn/%", start_date.isoformat(), end_date.isoformat()],
        ).fetchall()
        return [(r[0], float(r[1])) for r in rows if r and r[0] is not None and r[1] is not None]

    def _bank_loan_avg(self, start_date: date, end_date: date) -> list[tuple[date, float]]:
        max_pr = int(getattr(settings, "lai_suat_max_source_priority", 1))
        rows = self.db.con.execute(
            """
            WITH per_bank AS (
              SELECT
                date,
                bank_name,
                MIN(
                  CASE
                    WHEN rate_min_pct IS NOT NULL THEN rate_min_pct
                    WHEN rate_pct IS NOT NULL THEN rate_pct
                    WHEN rate_max_pct IS NOT NULL THEN rate_max_pct
                    ELSE NULL
                  END
                ) AS best_rate
              FROM bank_rates
              WHERE product_group = 'loan'
                AND (rate_min_pct IS NOT NULL OR rate_pct IS NOT NULL OR rate_max_pct IS NOT NULL)
                AND ((source_priority IS NULL OR source_priority <= ?) OR (source_url IS NOT NULL AND source_url LIKE ?))
                AND date >= ? AND date <= ?
              GROUP BY date, bank_name
            )
            SELECT date, AVG(best_rate) AS v
            FROM per_bank
            GROUP BY date
            ORDER BY date
            """,
            [int(max_pr), "%timo.vn/%", start_date.isoformat(), end_date.isoformat()],
        ).fetchall()
        return [(r[0], float(r[1])) for r in rows if r and r[0] is not None and r[1] is not None]

    def _transmission_metric(self, metric_name: str, start_date: date, end_date: date) -> list[tuple[date, float]]:
        rows = self.db.con.execute(
            """
            SELECT date, metric_value
            FROM transmission_daily_metrics
            WHERE metric_name = ?
              AND metric_value IS NOT NULL
              AND date >= ? AND date <= ?
            ORDER BY date
            """,
            [metric_name, start_date.isoformat(), end_date.isoformat()],
        ).fetchall()
        return [(r[0], float(r[1])) for r in rows if r and r[0] is not None and r[1] is not None]

    def _stress_index(self, start_date: date, end_date: date) -> list[tuple[date, float]]:
        rows = self.db.con.execute(
            """
            SELECT date, stress_index
            FROM bondy_stress_daily
            WHERE stress_index IS NOT NULL
              AND date >= ? AND date <= ?
            ORDER BY date
            """,
            [start_date.isoformat(), end_date.isoformat()],
        ).fetchall()
        return [(r[0], float(r[1])) for r in rows if r and r[0] is not None and r[1] is not None]

    def series_coverage(
        self,
        series_id: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        points = self.get_series(series_id, start_date, end_date)
        if not points:
            return {"series_id": series_id, "n_obs": 0, "start": None, "end": None}
        return {
            "series_id": series_id,
            "n_obs": len(points),
            "start": points[0][0].isoformat(),
            "end": points[-1][0].isoformat(),
        }

    def lead_lag(
        self,
        x_id: str,
        y_id: str,
        start_date: date,
        end_date: date,
        max_lag: int = 20,
        diff: bool = True,
    ) -> dict[str, Any]:
        x_pts = self.get_series(x_id, start_date, end_date)
        y_pts = self.get_series(y_id, start_date, end_date)

        x_map = {d: float(v) for d, v in x_pts if isinstance(v, (int, float))}
        y_map = {d: float(v) for d, v in y_pts if isinstance(v, (int, float))}

        dates = sorted(set(x_map.keys()) & set(y_map.keys()))
        n_overlap = len(dates)
        if len(dates) < 10:
            return {
                "x": x_id,
                "y": y_id,
                "diff": diff,
                "max_lag": max_lag,
                "n_obs": len(dates),
                "n_overlap": n_overlap,
                "m_tests": 0,
                "lags": list(range(-max_lag, max_lag + 1)),
                "correlations": [None] * (2 * max_lag + 1),
                "n_pairs_by_lag": [0] * (2 * max_lag + 1),
                "p_values": [None] * (2 * max_lag + 1),
                "p_values_adj": [None] * (2 * max_lag + 1),
                "ci95_low": [None] * (2 * max_lag + 1),
                "ci95_high": [None] * (2 * max_lag + 1),
                "best_lag": None,
                "best_corr": None,
                "best_n_pairs": None,
                "best_p_value": None,
                "best_p_value_adj": None,
                "best_ci95_low": None,
                "best_ci95_high": None,
                "stability": None,
                "warnings": ["not_enough_overlap_pairs"],
            }

        x_vals = [x_map[d] for d in dates]
        y_vals = [y_map[d] for d in dates]

        warnings: list[str] = []
        if diff:
            x_vals = [x_vals[i] - x_vals[i - 1] for i in range(1, len(x_vals))]
            y_vals = [y_vals[i] - y_vals[i - 1] for i in range(1, len(y_vals))]
            dates = dates[1:]
        else:
            warnings.append("diff_disabled_nonstationarity_risk")

        lags = list(range(-max_lag, max_lag + 1))
        corrs: list[Optional[float]] = []
        n_pairs_by_lag: list[int] = []
        for lag in lags:
            if lag < 0:
                xs = x_vals[-lag:]
                ys = y_vals[: len(x_vals) + lag]
            elif lag > 0:
                xs = x_vals[: len(x_vals) - lag]
                ys = y_vals[lag:]
            else:
                xs = x_vals
                ys = y_vals
            n_pairs_by_lag.append(min(len(xs), len(ys)))
            corrs.append(_pearson_corr(xs, ys))

        m_tests = sum(1 for c in corrs if c is not None)
        p_values: list[Optional[float]] = []
        p_values_adj: list[Optional[float]] = []
        ci95_low: list[Optional[float]] = []
        ci95_high: list[Optional[float]] = []
        for c, n_pairs in zip(corrs, n_pairs_by_lag):
            if c is None:
                p_values.append(None)
                p_values_adj.append(None)
                ci95_low.append(None)
                ci95_high.append(None)
                continue
            inf = _corr_inference(float(c), int(n_pairs), int(m_tests))
            p_values.append(inf["p_value"])
            p_values_adj.append(inf["p_value_adj"])
            ci95_low.append(inf["ci95_low"])
            ci95_high.append(inf["ci95_high"])

        best_lag = None
        best_corr = None
        best_abs = None
        best_n_pairs = None
        best_p_value = None
        best_p_value_adj = None
        best_ci95_low = None
        best_ci95_high = None
        for lag, c in zip(lags, corrs):
            if c is None:
                continue
            a = abs(c)
            if best_abs is None or a > best_abs:
                best_abs = a
                best_lag = lag
                best_corr = float(c)

        if best_lag is not None:
            idx = lags.index(best_lag)
            best_n_pairs = int(n_pairs_by_lag[idx]) if idx < len(n_pairs_by_lag) else None
            best_p_value = p_values[idx] if idx < len(p_values) else None
            best_p_value_adj = p_values_adj[idx] if idx < len(p_values_adj) else None
            best_ci95_low = ci95_low[idx] if idx < len(ci95_low) else None
            best_ci95_high = ci95_high[idx] if idx < len(ci95_high) else None

        if best_lag in (-max_lag, max_lag):
            warnings.append("best_lag_at_boundary")

        # Simple stability check: split sample into two chronological halves and compare "best lag".
        stability: Optional[dict[str, Any]] = None
        if len(x_vals) >= 40 and max_lag <= max(5, len(x_vals) - 10):
            split = len(x_vals) // 2
            x1, y1 = x_vals[:split], y_vals[:split]
            x2, y2 = x_vals[split:], y_vals[split:]

            def _best_for_slice(xv: list[float], yv: list[float]) -> tuple[Optional[int], Optional[float], Optional[int]]:
                slice_corrs: list[Optional[float]] = []
                slice_pairs: list[int] = []
                for lag in lags:
                    if lag < 0:
                        xs = xv[-lag:]
                        ys = yv[: len(xv) + lag]
                    elif lag > 0:
                        xs = xv[: len(xv) - lag]
                        ys = yv[lag:]
                    else:
                        xs = xv
                        ys = yv
                    slice_pairs.append(min(len(xs), len(ys)))
                    slice_corrs.append(_pearson_corr(xs, ys))

                b_lag = None
                b_corr = None
                b_abs = None
                b_n = None
                for lag, c, n in zip(lags, slice_corrs, slice_pairs):
                    if c is None:
                        continue
                    a = abs(c)
                    if b_abs is None or a > b_abs:
                        b_abs = a
                        b_lag = lag
                        b_corr = float(c)
                        b_n = int(n)
                return b_lag, b_corr, b_n

            b1_lag, b1_corr, b1_n = _best_for_slice(x1, y1)
            b2_lag, b2_corr, b2_n = _best_for_slice(x2, y2)

            consistent = False
            if b1_lag is not None and b2_lag is not None and b1_corr is not None and b2_corr is not None:
                lag_close = abs(int(b1_lag) - int(b2_lag)) <= 2
                sign_same = (b1_corr >= 0) == (b2_corr >= 0)
                consistent = bool(lag_close and sign_same)
                if not consistent:
                    warnings.append("unstable_best_lag_across_splits")

            stability = {
                "enabled": True,
                "split_index": int(split),
                "first": {"best_lag": b1_lag, "best_corr": b1_corr, "best_n_pairs": b1_n, "n_obs": int(len(x1))},
                "second": {"best_lag": b2_lag, "best_corr": b2_corr, "best_n_pairs": b2_n, "n_obs": int(len(x2))},
                "consistent": consistent,
            }
        else:
            stability = {"enabled": False, "reason": "not_enough_history_for_stability_check"}

        return {
            "x": x_id,
            "y": y_id,
            "diff": diff,
            "max_lag": max_lag,
            "n_obs": len(x_vals),
            "n_overlap": n_overlap,
            "m_tests": int(m_tests),
            "lags": lags,
            "correlations": corrs,
            "n_pairs_by_lag": n_pairs_by_lag,
            "p_values": p_values,
            "p_values_adj": p_values_adj,
            "ci95_low": ci95_low,
            "ci95_high": ci95_high,
            "best_lag": best_lag,
            "best_corr": best_corr,
            "best_n_pairs": best_n_pairs,
            "best_p_value": best_p_value,
            "best_p_value_adj": best_p_value_adj,
            "best_ci95_low": best_ci95_low,
            "best_ci95_high": best_ci95_high,
            "stability": stability,
            "warnings": warnings,
        }

    def granger(
        self,
        cause_id: str,
        effect_id: str,
        start_date: date,
        end_date: date,
        max_lag: int = 5,
        diff: bool = True,
    ) -> dict[str, Any]:
        try:
            import numpy as np  # type: ignore
            from statsmodels.tsa.stattools import grangercausalitytests  # type: ignore
        except Exception:
            return {
                "enabled": False,
                "reason": "statsmodels_unavailable",
                "cause": cause_id,
                "effect": effect_id,
            }

        x_pts = self.get_series(cause_id, start_date, end_date)
        y_pts = self.get_series(effect_id, start_date, end_date)

        x_map = {d: float(v) for d, v in x_pts if isinstance(v, (int, float))}
        y_map = {d: float(v) for d, v in y_pts if isinstance(v, (int, float))}
        dates = sorted(set(x_map.keys()) & set(y_map.keys()))
        if len(dates) < max_lag + 10:
            return {
                "enabled": True,
                "cause": cause_id,
                "effect": effect_id,
                "diff": diff,
                "max_lag": max_lag,
                "n_obs": len(dates),
                "reason": "not_enough_overlap",
                "results": [],
            }

        x_vals = [x_map[d] for d in dates]
        y_vals = [y_map[d] for d in dates]
        if diff:
            x_vals = [x_vals[i] - x_vals[i - 1] for i in range(1, len(x_vals))]
            y_vals = [y_vals[i] - y_vals[i - 1] for i in range(1, len(y_vals))]

        data = np.column_stack([y_vals, x_vals])  # tests: x causes y
        out: list[dict[str, Any]] = []
        try:
            res = grangercausalitytests(data, maxlag=max_lag, verbose=False)
            for lag in range(1, max_lag + 1):
                tests = res[lag][0]
                ssr_f = tests.get("ssr_ftest")
                if ssr_f:
                    fstat, pval, df_denom, df_num = ssr_f
                    out.append(
                        {
                            "lag": lag,
                            "test": "ssr_ftest",
                            "f": float(fstat),
                            "p_value": float(pval),
                            "df_denom": float(df_denom),
                            "df_num": float(df_num),
                        }
                    )
        except Exception as e:
            return {
                "enabled": True,
                "cause": cause_id,
                "effect": effect_id,
                "diff": diff,
                "max_lag": max_lag,
                "n_obs": len(y_vals),
                "reason": f"failed: {e}",
                "results": [],
            }

        best = min((r for r in out if isinstance(r.get("p_value"), float)), key=lambda r: r["p_value"], default=None)
        return {
            "enabled": True,
            "cause": cause_id,
            "effect": effect_id,
            "diff": diff,
            "max_lag": max_lag,
            "n_obs": len(y_vals),
            "reason": None,
            "best": best,
            "results": out,
        }

    def var_irf(
        self,
        variables: list[str],
        start_date: date,
        end_date: date,
        max_lag: int = 5,
        steps: int = 10,
        diff: bool = True,
    ) -> dict[str, Any]:
        try:
            import numpy as np  # type: ignore
            from statsmodels.tsa.api import VAR  # type: ignore
        except Exception:
            return {"enabled": False, "reason": "statsmodels_unavailable", "variables": variables}

        series_points = {vid: self.get_series(vid, start_date, end_date) for vid in variables}
        series_maps = {
            vid: {d: float(v) for d, v in pts if isinstance(v, (int, float))}
            for vid, pts in series_points.items()
        }
        common_dates = None
        for m in series_maps.values():
            dates = set(m.keys())
            common_dates = dates if common_dates is None else (common_dates & dates)

        dates_sorted = sorted(common_dates or [])
        if len(dates_sorted) < (max_lag + steps + 30):
            return {
                "enabled": True,
                "reason": "not_enough_overlap",
                "variables": variables,
                "n_obs": len(dates_sorted),
            }

        X = [[series_maps[vid][d] for vid in variables] for d in dates_sorted]
        if diff:
            X = [[X[i][j] - X[i - 1][j] for j in range(len(variables))] for i in range(1, len(X))]
            dates_sorted = dates_sorted[1:]

        arr = np.asarray(X, dtype=float)
        try:
            model = VAR(arr)
            sel = model.select_order(max_lag)
            lag = int(sel.aic) if getattr(sel, "aic", None) else max_lag
            lag = max(1, min(max_lag, lag))
            fit = model.fit(lag)
            irf = fit.irf(steps)
            irfs = irf.irfs  # shape: (steps+1, k, k)
        except Exception as e:
            return {"enabled": True, "reason": f"failed: {e}", "variables": variables}

        k = len(variables)
        out_irf: dict[str, Any] = {}
        for i_impulse in range(k):
            impulse = variables[i_impulse]
            out_irf[impulse] = {}
            for j_resp in range(k):
                resp = variables[j_resp]
                out_irf[impulse][resp] = [float(irfs[h, j_resp, i_impulse]) for h in range(irfs.shape[0])]

        return {
            "enabled": True,
            "reason": None,
            "variables": variables,
            "diff": diff,
            "max_lag": max_lag,
            "selected_lag": lag,
            "steps": steps,
            "n_obs": int(arr.shape[0]),
            "irf": out_irf,
        }

    def network_granger(
        self,
        variables: list[str],
        start_date: date,
        end_date: date,
        max_lag: int = 5,
        alpha: float = 0.05,
        diff: bool = True,
        max_edges: int = 30,
    ) -> dict[str, Any]:
        """
        Build a directed lead/causality network from pairwise Granger tests.
        Returns only statistically significant edges (p < alpha).
        """
        # Fast dependency check.
        try:
            import numpy as np  # noqa: F401  # type: ignore
            import statsmodels  # noqa: F401  # type: ignore
        except Exception:
            return {"enabled": False, "reason": "statsmodels_unavailable", "nodes": [], "edges": []}

        nodes = []
        labels = {s.id: s.label for s in SERIES_CATALOG}
        for vid in variables:
            nodes.append({"id": vid, "label": labels.get(vid, vid)})

        edges: list[dict[str, Any]] = []
        for cause in variables:
            for effect in variables:
                if cause == effect:
                    continue
                res = self.granger(
                    cause_id=cause,
                    effect_id=effect,
                    start_date=start_date,
                    end_date=end_date,
                    max_lag=max_lag,
                    diff=diff,
                )
                if not res.get("enabled"):
                    return {"enabled": False, "reason": res.get("reason") or "statsmodels_unavailable", "nodes": [], "edges": []}
                best = res.get("best")
                if not best or not isinstance(best.get("p_value"), float):
                    continue
                p = float(best["p_value"])
                if p < float(alpha):
                    edges.append(
                        {
                            "from": cause,
                            "to": effect,
                            "p_value": p,
                            "lag": int(best.get("lag") or 0),
                            "f": float(best.get("f") or 0.0),
                        }
                    )

        edges.sort(key=lambda e: (e["p_value"], -abs(e.get("f", 0.0))))
        if len(edges) > max_edges:
            edges = edges[:max_edges]

        return {
            "enabled": True,
            "reason": None,
            "alpha": float(alpha),
            "max_lag": int(max_lag),
            "diff": bool(diff),
            "nodes": nodes,
            "edges": edges,
        }

    def _yield_by_tenor(self, tenor: str, start_date: date, end_date: date) -> list[tuple[date, float]]:
        rows = self.db.con.execute(
            """
            SELECT date, AVG(spot_rate_annual) AS v
            FROM gov_yield_curve
            WHERE tenor_label = ?
              AND date >= ? AND date <= ?
              AND spot_rate_annual IS NOT NULL
            GROUP BY date
            ORDER BY date
            """,
            [tenor, start_date.isoformat(), end_date.isoformat()],
        ).fetchall()
        return [(d, float(v)) for d, v in rows if d is not None and isinstance(v, (int, float))]

    def _curve_slope_10y_2y(self, start_date: date, end_date: date) -> list[tuple[date, float]]:
        rows = self.db.con.execute(
            """
            SELECT
              date,
              AVG(CASE WHEN tenor_label = '10Y' THEN spot_rate_annual END) AS y10,
              AVG(CASE WHEN tenor_label = '2Y' THEN spot_rate_annual END) AS y2
            FROM gov_yield_curve
            WHERE date >= ? AND date <= ?
              AND tenor_label IN ('2Y','10Y')
              AND spot_rate_annual IS NOT NULL
            GROUP BY date
            HAVING y10 IS NOT NULL AND y2 IS NOT NULL
            ORDER BY date
            """,
            [start_date.isoformat(), end_date.isoformat()],
        ).fetchall()
        return [(d, float(y10) - float(y2)) for d, y10, y2 in rows if d is not None]

    def _interbank(self, tenor: str, start_date: date, end_date: date) -> list[tuple[date, float]]:
        rows = self.db.con.execute(
            """
            SELECT date, AVG(rate) AS v
            FROM interbank_rates
            WHERE tenor_label = ?
              AND date >= ? AND date <= ?
              AND rate IS NOT NULL
            GROUP BY date
            ORDER BY date
            """,
            [tenor, start_date.isoformat(), end_date.isoformat()],
        ).fetchall()
        return [(d, float(v)) for d, v in rows if d is not None and isinstance(v, (int, float))]

    def _policy_anchor_ffill(self, start_date: date, end_date: date) -> list[tuple[date, float]]:
        # Policy series is sparse; for daily research we forward-fill the last known anchor.
        rows = self.db.con.execute(
            """
            SELECT
              date,
              MAX(CASE WHEN rate_name = 'Refinancing Rate' THEN rate END) AS refinancing,
              MAX(CASE WHEN rate_name = 'Base Rate' THEN rate END) AS base,
              MAX(CASE WHEN rate_name = 'Rediscount Rate' THEN rate END) AS rediscount
            FROM policy_rates
            WHERE date <= ?
              AND rate IS NOT NULL
            GROUP BY date
            ORDER BY date
            """,
            [end_date.isoformat()],
        ).fetchall()

        policy_by_date: dict[date, float] = {}
        for d, refinancing, base, rediscount in rows:
            if d is None:
                continue
            anchor = refinancing if refinancing is not None else base if base is not None else rediscount
            if anchor is None:
                continue
            policy_by_date[d] = float(anchor)

        if not policy_by_date:
            return []

        out: list[tuple[date, float]] = []
        current = start_date
        last_anchor: Optional[float] = None
        while current <= end_date:
            if current in policy_by_date:
                last_anchor = policy_by_date[current]
            if last_anchor is not None:
                out.append((current, float(last_anchor)))
            current = current + timedelta(days=1)
        return out

    def _auction_btc(self, start_date: date, end_date: date) -> list[tuple[date, float]]:
        try:
            rows = self.db.con.execute(
                """
                SELECT date, median(bid_to_cover) AS v
                FROM gov_auction_results
                WHERE date >= ? AND date <= ?
                  AND bid_to_cover IS NOT NULL
                GROUP BY date
                ORDER BY date
                """,
                [start_date.isoformat(), end_date.isoformat()],
            ).fetchall()
        except Exception:
            rows = self.db.con.execute(
                """
                SELECT date, quantile_cont(bid_to_cover, 0.5) AS v
                FROM gov_auction_results
                WHERE date >= ? AND date <= ?
                  AND bid_to_cover IS NOT NULL
                GROUP BY date
                ORDER BY date
                """,
                [start_date.isoformat(), end_date.isoformat()],
            ).fetchall()
        return [(d, float(v)) for d, v in rows if d is not None and isinstance(v, (int, float))]

    def _auction_sold(self, start_date: date, end_date: date) -> list[tuple[date, float]]:
        rows = self.db.con.execute(
            """
            SELECT date, SUM(amount_sold) AS v
            FROM gov_auction_results
            WHERE date >= ? AND date <= ?
              AND amount_sold IS NOT NULL
            GROUP BY date
            ORDER BY date
            """,
            [start_date.isoformat(), end_date.isoformat()],
        ).fetchall()
        return [(d, float(v)) for d, v in rows if d is not None and isinstance(v, (int, float))]

    def _secondary_value(self, start_date: date, end_date: date) -> list[tuple[date, float]]:
        rows = self.db.con.execute(
            """
            SELECT date, SUM(value) AS v
            FROM gov_secondary_trading
            WHERE date >= ? AND date <= ?
              AND value IS NOT NULL
            GROUP BY date
            ORDER BY date
            """,
            [start_date.isoformat(), end_date.isoformat()],
        ).fetchall()
        return [(d, float(v)) for d, v in rows if d is not None and isinstance(v, (int, float))]

    def _global(self, series_id: str, start_date: date, end_date: date) -> list[tuple[date, float]]:
        rows = self.db.con.execute(
            """
            SELECT date, value
            FROM global_rates_daily
            WHERE series_id = ?
              AND date >= ? AND date <= ?
              AND value IS NOT NULL
            ORDER BY date
            """,
            [series_id, start_date.isoformat(), end_date.isoformat()],
        ).fetchall()
        return [(d, float(v)) for d, v in rows if d is not None and isinstance(v, (int, float))]
