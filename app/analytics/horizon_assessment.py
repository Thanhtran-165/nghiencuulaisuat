"""
Horizon Assessment Engine (Phase 1)
Implements "Nhận định 3 thời hạn" using observation-based horizons ("phiên"),
date-aligned valid pairs, primary-series readiness, and transparent fallbacks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional
import os
import statistics
from datetime import datetime


SOURCE_PRIORITY: dict[str, int] = {
    "SBV": 1,
    "HNX": 2,
    "HNX_YC": 2,
    "HSX": 3,
    "ABO": 4,
    "VND": 5,
    "TCBS": 6,
    "unknown": 99,
}


HORIZON_PHIEN: dict[str, dict[str, Any]] = {
    "short": {"now": [7, 14], "soon": 7, "min_pairs": 20},
    "mid": {"now": [30, 60], "soon": 14, "min_pairs": 30},
    "long": {"now": [90, 180], "soon": 30, "min_pairs": 45},
}


HORIZON_LABELS: dict[str, dict[str, str]] = {
    "short": {
        "title": "Ngắn hạn",
        "subtitle": "~0-1 tháng, 7-14 phiên gần nhất",
        "explanation": "Áp lực lãi suất vay ngắn hạn (tính theo phiên, không phải calendar days).",
    },
    "mid": {
        "title": "Trung hạn",
        "subtitle": "~1-6 tháng, 30-60 phiên gần nhất",
        "explanation": "Xu hướng mặt bằng lãi suất (tính theo phiên, không phải calendar days).",
    },
    "long": {
        "title": "Dài hạn",
        "subtitle": "~6-24 tháng, 90-180 phiên gần nhất",
        "explanation": "Mặt bằng dài hạn & rủi ro (tính theo phiên, không phải calendar days).",
    },
}


PRIMARY_SERIES: dict[str, dict[str, Any]] = {
    "short": {
        "required": "IB_ON",
        "optional": ["IB_1W", "IB_1M"],
        "fallback": "IB_1W",
    },
    "mid": {
        "required": "YIELD_2Y",
        "optional": ["YIELD_5Y", "SLOPE_10Y_2Y"],
        "fallback": "YIELD_5Y",
    },
    "long": {
        "required": "YIELD_10Y",
        "optional": ["TERM_PREMIUM_PROXY", "POLICY_RATE"],
        "fallback": None,
    },
}


INFORMATION_ONLY_LANGUAGE: dict[str, dict[str, str]] = {
    "short": {
        "loosening": "Áp lực lãi suất ngắn hạn giảm → môi trường có xu hướng thuận lợi hơn so với gần đây",
        "neutral": "Áp lực ổn định → điều kiện vay không thay đổi đáng kể",
        "tightening": "Áp lực tăng → rủi ro chi phí vay tăng trong ngắn hạn",
    },
    "mid": {
        "up": "Xu hướng mặt bằng lãi suất nghiêng tăng → điều kiện cho vay có thể trở nên chặt hơn",
        "stable": "Xu hướng ổn định → mặt bằng lãi suất không có thay đổi lớn",
        "down": "Xu hướng nghiêng giảm → điều kiện cho vay có thể thuận lợi hơn",
    },
    "long": {
        "high": "Mặt bằng dài hạn ở vùng cao tương đối so với lịch sử quan sát",
        "medium": "Mặt bằng ở mức trung bình so với lịch sử quan sát",
        "low": "Mặt bằng ở vùng thấp tương đối so với lịch sử quan sát",
    },
}


def _as_str(d: Any) -> str:
    if isinstance(d, date):
        return d.isoformat()
    return str(d)


def canonicalize_series(
    raw_records: list[dict[str, Any]],
    source_priority: dict[str, int] = SOURCE_PRIORITY,
) -> list[dict[str, Any]]:
    """
    Canonicalize: each date keeps a single observation by source priority, then newest fetched_at.
    Accepts records with keys: date, value, source, fetched_at (optional).
    """
    by_date: dict[str, dict[str, Any]] = {}
    for r in raw_records or []:
        if not r:
            continue
        d = r.get("date")
        v = r.get("value")
        if d is None:
            continue
        if not isinstance(v, (int, float)):
            continue
        src = r.get("source") or "unknown"
        fetched_at = r.get("fetched_at")
        key = _as_str(d)

        candidate = {"date": key, "value": float(v), "source": str(src), "fetched_at": fetched_at}
        existing = by_date.get(key)
        if existing is None:
            by_date[key] = candidate
            continue

        cur_pr = int(source_priority.get(str(existing.get("source") or "unknown"), 99))
        new_pr = int(source_priority.get(str(src), 99))
        if new_pr < cur_pr:
            by_date[key] = candidate
            continue
        if new_pr > cur_pr:
            continue

        # Same priority: keep latest fetched_at if present, else keep existing.
        if fetched_at and (not existing.get("fetched_at") or str(fetched_at) > str(existing.get("fetched_at"))):
            by_date[key] = candidate

    out = list(by_date.values())
    out.sort(key=lambda x: x["date"])
    return out


def prefer_sources_if_present(
    canonical_series: list[dict[str, Any]],
    preferred_sources: set[str],
) -> list[dict[str, Any]]:
    """
    If any observation exists with a preferred source, keep only those rows.
    This matches the idea of an "official/canonical" series even if a fallback
    source provides newer-but-less-official updates on some dates.
    """
    if not canonical_series:
        return []
    preferred = [r for r in canonical_series if str(r.get("source") or "").strip() in preferred_sources]
    return preferred if preferred else canonical_series


def calculate_valid_pairs_date_aligned(series: list[dict[str, Any]], horizon_phien: int) -> dict[str, Any]:
    """
    Date-aligned valid pairs for observation-based horizons:
    count i where both value[i] and value[i+h] are present.
    """
    s = series or []
    valid_pairs = 0
    valid_indices: list[tuple[int, int]] = []
    for i in range(0, max(0, len(s) - int(horizon_phien))):
        a = s[i].get("value")
        b = s[i + int(horizon_phien)].get("value")
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            valid_pairs += 1
            valid_indices.append((i, i + int(horizon_phien)))

    date_range = {
        "start": s[0]["date"] if s else None,
        "end": s[-1]["date"] if s else None,
    }
    return {"valid_pairs": valid_pairs, "valid_indices": valid_indices, "date_range": date_range}


def _quantiles(values: list[float]) -> Optional[dict[str, float]]:
    if not values:
        return None
    v = sorted(values)
    if len(v) < 2:
        return None

    def q(p: float) -> float:
        pos = (len(v) - 1) * p
        lo = int(pos)
        hi = min(lo + 1, len(v) - 1)
        w = pos - lo
        return float(v[lo] * (1 - w) + v[hi] * w)

    return {"p20": q(0.20), "p40": q(0.40), "p60": q(0.60), "p80": q(0.80)}


def _classify_bucket_from_quantiles(value: float, qs: dict[str, float]) -> str:
    # B0 loose ... B4 tight (higher value => tighter) for rates.
    if value <= float(qs["p20"]):
        return "B0"
    if value <= float(qs["p40"]):
        return "B1"
    if value <= float(qs["p60"]):
        return "B2"
    if value <= float(qs["p80"]):
        return "B3"
    return "B4"


def _simple_direction(delta: float, eps: float) -> str:
    if delta > eps:
        return "up"
    if delta < -eps:
        return "down"
    return "stable"


def _confidence_level(x: float) -> str:
    if x >= 0.8:
        return "Cao"
    if x >= 0.5:
        return "Vừa"
    return "Thấp"


@dataclass
class HorizonResult:
    horizon_type: str
    labels: dict[str, str]
    status: str  # ready|fallback|limited
    primary_series: str
    primary_source: str
    horizon_used: int
    valid_pairs: int
    required_pairs: int
    conclusion: str
    trend_direction: str
    delta_bps: Optional[float]
    current_value: Optional[float]
    confidence_data: float
    confidence_model: float
    evidence: dict[str, Any]
    stress_overlay: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon_type": self.horizon_type,
            "labels": self.labels,
            "status": self.status,
            "primary": {
                "id": self.primary_series,
                "source": self.primary_source,
            },
            "readiness": {
                "horizon_used": self.horizon_used,
                "horizon_label": f"Δ{self.horizon_used} phiên",
                "valid_pairs": self.valid_pairs,
                "required_pairs": self.required_pairs,
            },
            "conclusion": self.conclusion,
            "trend": {
                "direction": self.trend_direction,
                "delta_bps": self.delta_bps,
                "compare_horizon": self.horizon_used,
            },
            "current_value": self.current_value,
            "confidence": {
                "data": self.confidence_data,
                "model": self.confidence_model,
                "data_level": _confidence_level(self.confidence_data),
                "model_level": _confidence_level(self.confidence_model),
            },
            "stress_overlay": self.stress_overlay,
            "evidence": self.evidence,
        }


class HorizonAssessmentEngine:
    def __init__(self, db_manager):
        self.db = db_manager

    def build_payload(self) -> dict[str, Any]:
        as_of = date.today().isoformat()
        out: dict[str, Any] = {
            "as_of": as_of,
            "computed_at": datetime.now().isoformat(),
            "horizons": {},
        }
        for horizon_type in ("short", "mid", "long"):
            out["horizons"][horizon_type] = self.assess_horizon(horizon_type).to_dict()

        # Phase 3: lightweight linkage to overall VM-CI (if available).
        out["vmci_overall"] = self._vmci_overall_snapshot()
        return out

    def assess_horizon(self, horizon_type: str) -> HorizonResult:
        labels = dict(HORIZON_LABELS.get(horizon_type, {}))
        required_pairs = int(HORIZON_PHIEN[horizon_type]["min_pairs"])
        horizons = list(HORIZON_PHIEN[horizon_type]["now"])
        horizons.sort(reverse=True)  # prefer longer

        primary_id = PRIMARY_SERIES[horizon_type]["required"]
        fallback_id = PRIMARY_SERIES[horizon_type].get("fallback")
        raw_primary = self._fetch_series(primary_id)
        primary_canon = canonicalize_series(raw_primary)
        used_primary_id = primary_id

        if not primary_canon and fallback_id:
            raw_fb = self._fetch_series(str(fallback_id))
            primary_canon = canonicalize_series(raw_fb)
            used_primary_id = str(fallback_id)

        # Prefer official sources over time when present
        if horizon_type in {"mid", "long"}:
            primary_canon = prefer_sources_if_present(primary_canon, {"HNX", "HNX_YC"})
        if horizon_type == "short":
            primary_canon = prefer_sources_if_present(primary_canon, {"SBV"})
        if not primary_canon:
            return self._limited(
                horizon_type=horizon_type,
                labels=labels,
                primary_id=used_primary_id,
                required_pairs=required_pairs,
                reason=f"Thiếu primary series: {primary_id}",
            )

        selected_h = None
        selected_pairs = None
        for h in horizons:
            pairs = calculate_valid_pairs_date_aligned(primary_canon, int(h))
            if int(pairs["valid_pairs"]) >= required_pairs:
                selected_h = int(h)
                selected_pairs = pairs
                break

        # fallback: try shorter horizons explicitly
        if selected_h is None:
            for h in sorted(horizons):
                pairs = calculate_valid_pairs_date_aligned(primary_canon, int(h))
                if int(pairs["valid_pairs"]) >= required_pairs:
                    selected_h = int(h)
                    selected_pairs = pairs
                    break

        # if still none: limited
        if selected_h is None or selected_pairs is None:
            h0 = int(min(horizons))
            pairs0 = calculate_valid_pairs_date_aligned(primary_canon, h0)
            return self._limited(
                horizon_type=horizon_type,
                labels=labels,
                primary_id=used_primary_id,
                required_pairs=required_pairs,
                reason=f"Chỉ có {pairs0['valid_pairs']}/{required_pairs} cặp quan sát hợp lệ cho Δ{h0} phiên",
                primary_series=primary_canon,
                horizon_used=h0,
                valid_pairs=int(pairs0["valid_pairs"]),
            )

        # compute metrics on selected horizon
        last = primary_canon[-1]
        past = primary_canon[-1 - selected_h] if len(primary_canon) > selected_h else None
        current_value = float(last["value"])
        past_value = float(past["value"]) if past and isinstance(past.get("value"), (int, float)) else None
        delta = (current_value - past_value) if past_value is not None else None
        delta_bps = (delta * 100.0) if delta is not None else None

        # bucket: train-only quantiles on values (last 180 observations excluding current)
        lookback = int(os.getenv("INSIGHTS_BUCKET_LOOKBACK", "180"))
        min_n = int(os.getenv("INSIGHTS_BUCKET_MIN_N", "60"))
        train = [float(r["value"]) for r in primary_canon[-1 - lookback : -1] if isinstance(r.get("value"), (int, float))]
        bucket = None
        qs = None
        if len(train) >= min_n:
            qs = _quantiles(train)
            if qs is not None:
                bucket = _classify_bucket_from_quantiles(current_value, qs)

        # direction
        eps = float(os.getenv("INSIGHTS_TREND_EPS_BPS", "3.0"))
        trend_direction = "stable"
        if delta_bps is not None:
            trend_direction = _simple_direction(delta_bps, eps=eps)

        # conclusion: information-only language
        conclusion = self._generate_conclusion(horizon_type, bucket=bucket, trend_direction=trend_direction)

        primary_source = str(last.get("source") or "unknown")
        status = "ready"
        # Note: if selected_h is not the maximum horizon -> fallback status.
        if selected_h != int(max(horizons)):
            status = "fallback"

        data_conf = min(1.0, float(selected_pairs["valid_pairs"]) / float(required_pairs)) if required_pairs > 0 else 0.0
        model_conf = 0.4
        if bucket is not None:
            model_conf = 0.7
        if qs is not None and len(train) >= min_n and (max(train) - min(train)) > 1e-9:
            model_conf = min(0.85, model_conf + 0.1)

        evidence = self._collect_evidence(
            horizon_type=horizon_type,
            primary_id=primary_id,
            primary_series=primary_canon,
            horizon_used=selected_h,
            bucket=bucket,
            qs=qs,
            train_n=len(train),
            delta_bps=delta_bps,
        )

        # Optional: stress overlay (Phase 1 uses a lightweight z-score on stress_index series if available).
        stress_overlay = self._stress_overlay_if_any()
        if stress_overlay and stress_overlay.get("active"):
            # adjust confidence and prefix conclusion
            model_conf = max(0.1, model_conf * 0.7)
            data_conf = max(0.2, data_conf * 0.8)
            conclusion = f"{stress_overlay.get('label')}: {conclusion}"

        # Phase 2/3: OOS diagnostics (gated by min pairs)
        oos = self._oos_diagnostics(primary_canon, horizon_phien=selected_h, min_oos=20, min_train=60)
        if oos:
            evidence["oos"] = oos
            # Nudge model confidence when OOS beats random-walk baseline clearly.
            if oos.get("significant_vs_baseline"):
                model_conf = min(0.9, model_conf + 0.1)

        return HorizonResult(
            horizon_type=horizon_type,
            labels=labels,
            status=status,
            primary_series=used_primary_id,
            primary_source=primary_source,
            horizon_used=selected_h,
            valid_pairs=int(selected_pairs["valid_pairs"]),
            required_pairs=required_pairs,
            conclusion=conclusion,
            trend_direction=trend_direction,
            delta_bps=delta_bps,
            current_value=current_value,
            confidence_data=data_conf,
            confidence_model=model_conf,
            evidence=evidence,
            stress_overlay=stress_overlay,
        )

    def _generate_conclusion(self, horizon_type: str, bucket: Optional[str], trend_direction: str) -> str:
        if horizon_type == "short":
            # Use delta direction primarily for short horizon.
            if trend_direction == "up":
                return INFORMATION_ONLY_LANGUAGE["short"]["tightening"]
            if trend_direction == "down":
                return INFORMATION_ONLY_LANGUAGE["short"]["loosening"]
            return INFORMATION_ONLY_LANGUAGE["short"]["neutral"]

        if horizon_type == "mid":
            if trend_direction == "up":
                return INFORMATION_ONLY_LANGUAGE["mid"]["up"]
            if trend_direction == "down":
                return INFORMATION_ONLY_LANGUAGE["mid"]["down"]
            return INFORMATION_ONLY_LANGUAGE["mid"]["stable"]

        # long: bucket if available, else trend
        if bucket in {"B3", "B4"}:
            return INFORMATION_ONLY_LANGUAGE["long"]["high"]
        if bucket in {"B0", "B1"}:
            return INFORMATION_ONLY_LANGUAGE["long"]["low"]
        if bucket == "B2":
            return INFORMATION_ONLY_LANGUAGE["long"]["medium"]
        if trend_direction == "up":
            return INFORMATION_ONLY_LANGUAGE["long"]["high"]
        if trend_direction == "down":
            return INFORMATION_ONLY_LANGUAGE["long"]["low"]
        return INFORMATION_ONLY_LANGUAGE["long"]["medium"]

    def _limited(
        self,
        horizon_type: str,
        labels: dict[str, str],
        primary_id: str,
        required_pairs: int,
        reason: str,
        primary_series: Optional[list[dict[str, Any]]] = None,
        horizon_used: int = 0,
        valid_pairs: int = 0,
    ) -> HorizonResult:
        primary_source = "unknown"
        current_value = None
        delta_bps = None
        trend_direction = "stable"
        if primary_series:
            last = primary_series[-1]
            primary_source = str(last.get("source") or "unknown")
            current_value = float(last["value"])
            if horizon_used and len(primary_series) > horizon_used:
                past = primary_series[-1 - int(horizon_used)]
                delta_bps = (float(last["value"]) - float(past["value"])) * 100.0
                trend_direction = _simple_direction(delta_bps, eps=float(os.getenv("INSIGHTS_TREND_EPS_BPS", "3.0")))

        evidence = {
            "reason": reason,
            "limitations": [
                reason,
                "Dữ liệu được canonicalize: mỗi ngày chỉ lấy 1 observation theo source priority.",
            ],
        }
        return HorizonResult(
            horizon_type=horizon_type,
            labels=labels,
            status="limited",
            primary_series=primary_id,
            primary_source=primary_source,
            horizon_used=horizon_used,
            valid_pairs=valid_pairs,
            required_pairs=required_pairs,
            conclusion="Data chưa đủ để đánh giá.",
            trend_direction=trend_direction,
            delta_bps=delta_bps,
            current_value=current_value,
            confidence_data=0.2,
            confidence_model=0.2,
            evidence=evidence,
            stress_overlay=self._stress_overlay_if_any(),
        )

    def _fetch_series(self, series_id: str) -> list[dict[str, Any]]:
        """
        Fetch raw series from DB in a common shape: {date, value, source, fetched_at}.
        """
        if series_id == "IB_ON":
            rows = self.db.con.execute(
                """
                SELECT date, rate, source, fetched_at
                FROM interbank_rates
                WHERE tenor_label = 'ON' AND rate IS NOT NULL
                ORDER BY date ASC, fetched_at ASC
                """
            ).fetchall()
            return [{"date": r[0], "value": float(r[1]), "source": r[2], "fetched_at": r[3]} for r in rows]
        if series_id == "IB_1W":
            rows = self.db.con.execute(
                """
                SELECT date, rate, source, fetched_at
                FROM interbank_rates
                WHERE tenor_label = '1W' AND rate IS NOT NULL
                ORDER BY date ASC, fetched_at ASC
                """
            ).fetchall()
            return [{"date": r[0], "value": float(r[1]), "source": r[2], "fetched_at": r[3]} for r in rows]
        if series_id == "IB_1M":
            rows = self.db.con.execute(
                """
                SELECT date, rate, source, fetched_at
                FROM interbank_rates
                WHERE tenor_label = '1M' AND rate IS NOT NULL
                ORDER BY date ASC, fetched_at ASC
                """
            ).fetchall()
            return [{"date": r[0], "value": float(r[1]), "source": r[2], "fetched_at": r[3]} for r in rows]
        if series_id == "YIELD_2Y":
            rows = self.db.con.execute(
                """
                SELECT date, source, AVG(spot_rate_annual) AS v, MAX(fetched_at) AS fetched_at
                FROM gov_yield_curve
                WHERE tenor_label = '2Y' AND spot_rate_annual IS NOT NULL
                GROUP BY date, source
                ORDER BY date ASC
                """
            ).fetchall()
            return [{"date": r[0], "value": float(r[2]), "source": r[1] or "unknown", "fetched_at": r[3]} for r in rows]
        if series_id == "YIELD_5Y":
            rows = self.db.con.execute(
                """
                SELECT date, source, AVG(spot_rate_annual) AS v, MAX(fetched_at) AS fetched_at
                FROM gov_yield_curve
                WHERE tenor_label = '5Y' AND spot_rate_annual IS NOT NULL
                GROUP BY date, source
                ORDER BY date ASC
                """
            ).fetchall()
            return [{"date": r[0], "value": float(r[2]), "source": r[1] or "unknown", "fetched_at": r[3]} for r in rows]
        if series_id == "YIELD_10Y":
            rows = self.db.con.execute(
                """
                SELECT date, source, AVG(spot_rate_annual) AS v, MAX(fetched_at) AS fetched_at
                FROM gov_yield_curve
                WHERE tenor_label = '10Y' AND spot_rate_annual IS NOT NULL
                GROUP BY date, source
                ORDER BY date ASC
                """
            ).fetchall()
            return [{"date": r[0], "value": float(r[2]), "source": r[1] or "unknown", "fetched_at": r[3]} for r in rows]

        if series_id == "POLICY_RATE":
            rows = self.db.con.execute(
                """
                SELECT date, MAX(rate) AS rate, MAX(source) AS source, MAX(fetched_at) AS fetched_at
                FROM policy_rates
                WHERE rate IS NOT NULL
                GROUP BY date
                ORDER BY date ASC
                """
            ).fetchall()
            return [{"date": r[0], "value": float(r[1]), "source": r[2] or "SBV", "fetched_at": r[3]} for r in rows]

        return []

    def _collect_evidence(
        self,
        horizon_type: str,
        primary_id: str,
        primary_series: list[dict[str, Any]],
        horizon_used: int,
        bucket: Optional[str],
        qs: Optional[dict[str, float]],
        train_n: int,
        delta_bps: Optional[float],
    ) -> dict[str, Any]:
        last = primary_series[-1]
        limitations: list[str] = []
        if bucket is None:
            limitations.append("Bucket đang hiệu chỉnh (chưa đủ lịch sử).")
        limitations.append("Dữ liệu được canonicalize: mỗi ngày chỉ lấy 1 observation theo source priority.")

        evidence = {
            "primary_series": {
                "id": primary_id,
                "source": last.get("source") or "unknown",
                "as_of": last.get("date"),
                "n_dates": len(primary_series),
            },
            "horizon_used": horizon_used,
            "bucket": bucket,
            "bucket_meta": {
                "train_n": train_n,
                "p20": qs.get("p20") if qs else None,
                "p40": qs.get("p40") if qs else None,
                "p60": qs.get("p60") if qs else None,
                "p80": qs.get("p80") if qs else None,
            },
            "delta_bps": delta_bps,
            "limitations": limitations,
        }

        # Optional series availability (Phase 1: report only)
        optional_ids = list(PRIMARY_SERIES[horizon_type].get("optional", []))
        optional_available = []
        for oid in optional_ids:
            raw = self._fetch_series(oid)
            canon = canonicalize_series(raw) if raw else []
            if canon:
                optional_available.append({"id": oid, "source": canon[-1].get("source") or "unknown"})
        evidence["optional_series"] = optional_available
        if len(optional_available) < len(optional_ids):
            missing = sorted(set(optional_ids) - {o["id"] for o in optional_available})
            if missing:
                evidence["limitations"].append(f"Thiếu optional series: {', '.join(missing)}")

        # Term premium proxy for long horizon if possible
        if horizon_type == "long":
            proxy = self._term_premium_proxy()
            if proxy:
                evidence["term_premium_proxy"] = proxy
        return evidence

    def _term_premium_proxy(self) -> Optional[dict[str, Any]]:
        """
        Term premium proxy (transparent): prefer 10Y - policy; fallback 10Y - 1M.
        Returned unit: percentage points.
        """
        y10 = self._fetch_series("YIELD_10Y")
        if not y10:
            return None
        y10c = canonicalize_series(y10)
        if not y10c:
            return None

        long_rate = float(y10c[-1]["value"])

        pol = canonicalize_series(self._fetch_series("POLICY_RATE"))
        if pol:
            policy_rate = float(pol[-1]["value"])
            return {
                "value": long_rate - policy_rate,
                "label": "proxy chênh lệch dài–ngắn (10Y − policy rate)",
                "note": "Sử dụng policy rate làm anchor ngắn hạn. Đây là proxy thực nghiệm, không phải term premium chuẩn trong mô hình cấu trúc.",
                "components": {"long_rate": long_rate, "anchor": policy_rate, "anchor_type": "policy"},
            }

        ib1m = canonicalize_series(self._fetch_series("IB_1M"))
        if ib1m:
            short_anchor = float(ib1m[-1]["value"])
            return {
                "value": long_rate - short_anchor,
                "label": "proxy chênh lệch dài–ngắn (10Y − 1M)",
                "note": "Sử dụng lãi suất 1 tháng làm anchor (fallback). Proxy này không tách được risk premium từ expectations.",
                "components": {"long_rate": long_rate, "anchor": short_anchor, "anchor_type": "market"},
            }

        # Fallback 2: median short (ON/1W/1M) if any
        shorts: list[float] = []
        for sid in ("IB_ON", "IB_1W", "IB_1M"):
            s = canonicalize_series(self._fetch_series(sid))
            if s:
                shorts.append(float(s[-1]["value"]))
        if shorts:
            anchor = float(statistics.median(shorts))
            return {
                "value": long_rate - anchor,
                "label": "proxy chênh lệch dài–ngắn (10Y − median short)",
                "note": "Sử dụng median các lãi suất ngắn hạn (ON/1W/1M). Robust với outlier nhưng vẫn là proxy thực nghiệm.",
                "components": {"long_rate": long_rate, "anchor": anchor, "anchor_type": "market_median"},
            }

        return None

    def _stress_overlay_if_any(self) -> Optional[dict[str, Any]]:
        """
        Lightweight stress overlay based on BondY stress_index time series.
        Returns active=True when z > threshold, with a qualitative label.
        """
        threshold = float(os.getenv("INSIGHTS_STRESS_Z_THRESHOLD", "1.8"))
        method = os.getenv("INSIGHTS_STRESS_Z_METHOD", "std").strip().lower()  # std|mad
        winsor_limit = float(os.getenv("INSIGHTS_STRESS_WINSOR_LIMIT", "0.05"))
        try:
            rows = self.db.con.execute(
                """
                SELECT date, stress_index
                FROM bondy_stress
                WHERE stress_index IS NOT NULL
                ORDER BY date DESC
                LIMIT 200
                """
            ).fetchall()
            if not rows:
                return None
            values = [float(r[1]) for r in rows if r and r[1] is not None]
            if len(values) < 10:
                return None
            # winsorize to reduce heavy-tail impact
            if winsor_limit > 0 and len(values) >= 20:
                vv = sorted(values)
                k = int(len(vv) * winsor_limit)
                lo = vv[k]
                hi = vv[-1 - k]
                values_w = [min(max(v, lo), hi) for v in values]
            else:
                values_w = values

            latest = float(values_w[0])
            if method == "mad":
                med = statistics.median(values_w)
                abs_dev = [abs(v - med) for v in values_w]
                mad = statistics.median(abs_dev) if abs_dev else 0.0
                denom = (mad * 1.4826) if mad and mad > 0 else 0.0
                z = 0.0 if denom <= 0 else (latest - float(med)) / float(denom)
            else:
                mean = statistics.mean(values_w)
                stdev = statistics.stdev(values_w) if len(values_w) > 1 else 0.0
                z = 0.0 if stdev <= 0 else (latest - mean) / stdev
            if z <= threshold:
                return {"active": False, "stress_z": z, "method": method, "winsor_limit": winsor_limit}
            return {
                "active": True,
                "label": "⚠️ Chế độ nhiễu",
                "stress_z": z,
                "method": method,
                "winsor_limit": winsor_limit,
                "explanation": "Thị trường đang trong giai đoạn biến động cao. Tín hiệu lãi suất có thể bị méo do liquidity shock.",
                "implication": "Diễn giải cần thận trọng, tập trung vào thanh khoản hơn là trend dài hạn.",
            }
        except Exception:
            return None

    def _vmci_overall_snapshot(self) -> Optional[dict[str, Any]]:
        """
        Pull the latest overall VM-CI (computed in transmission metrics) if present.
        """
        try:
            rows = self.db.con.execute(
                """
                SELECT metric_name, metric_value, metric_value_text, source_components
                FROM transmission_daily_metrics
                WHERE date = (SELECT MAX(date) FROM transmission_daily_metrics)
                  AND metric_name IN ('vmci_now_score','vmci_now_bucket')
                """
            ).fetchall()
            if not rows:
                return None
            out: dict[str, Any] = {}
            for name, v, vt, sc in rows:
                if name == "vmci_now_score":
                    out["score"] = float(v) if v is not None else None
                if name == "vmci_now_bucket":
                    out["bucket"] = vt
                    out["meta"] = sc
            return out or None
        except Exception:
            return None

    def _oos_diagnostics(
        self,
        primary_series: list[dict[str, Any]],
        horizon_phien: int,
        min_oos: int,
        min_train: int,
    ) -> Optional[dict[str, Any]]:
        """
        Simple rolling/expanding OOS check (information-only; not a forecast):
        X_t = level(t), y_t = level(t+h) - level(t) (bps).
        Baselines: random-walk (0 change) and historical mean of y_train.
        """
        s = primary_series or []
        h = int(horizon_phien)
        if h <= 0:
            return None
        if len(s) < (min_train + min_oos + h + 1):
            return None

        x: list[float] = []
        y: list[float] = []
        for i in range(0, len(s) - h):
            a = s[i].get("value")
            b = s[i + h].get("value")
            if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
                continue
            x.append(float(a))
            y.append((float(b) - float(a)) * 100.0)  # bps

        if len(x) < (min_train + min_oos):
            return None

        preds_vmci: list[float] = []
        preds_rw: list[float] = []
        preds_mean: list[float] = []
        actuals: list[float] = []

        # expanding window
        for t in range(min_train, len(x)):
            x_train = x[:t]
            y_train = y[:t]
            if len(y_train) < 10:
                continue
            # OLS slope/intercept
            mean_x = statistics.mean(x_train)
            mean_y = statistics.mean(y_train)
            var_x = statistics.pvariance(x_train)
            if var_x <= 0:
                slope = 0.0
                intercept = mean_y
            else:
                cov_xy = statistics.mean([(xi - mean_x) * (yi - mean_y) for xi, yi in zip(x_train, y_train)])
                slope = cov_xy / var_x
                intercept = mean_y - slope * mean_x

            yhat = intercept + slope * x[t]
            preds_vmci.append(float(yhat))
            preds_rw.append(0.0)
            preds_mean.append(float(mean_y))
            actuals.append(float(y[t]))

        if len(actuals) < min_oos:
            return None

        def r2(a: list[float], p: list[float]) -> float:
            mean_a = statistics.mean(a)
            sst = sum((v - mean_a) ** 2 for v in a)
            if sst <= 0:
                return 0.0
            sse = sum((v - u) ** 2 for v, u in zip(a, p))
            return 1.0 - (sse / sst)

        def mae(a: list[float], p: list[float]) -> float:
            return float(statistics.mean([abs(v - u) for v, u in zip(a, p)]))

        r2_vmci = r2(actuals, preds_vmci)
        r2_rw = r2(actuals, preds_rw)
        r2_mean = r2(actuals, preds_mean)
        mae_vmci = mae(actuals, preds_vmci)
        mae_rw = mae(actuals, preds_rw)
        mae_mean = mae(actuals, preds_mean)

        significant = (r2_vmci - r2_rw) >= float(os.getenv("INSIGHTS_OOS_R2_IMPROVE", "0.05"))

        return {
            "horizon_phien": h,
            "n_oos": len(actuals),
            "metrics": {
                "vmci_linear": {"r2": r2_vmci, "mae": mae_vmci},
                "baseline_random_walk": {"r2": r2_rw, "mae": mae_rw},
                "baseline_mean": {"r2": r2_mean, "mae": mae_mean},
            },
            "significant_vs_baseline": bool(significant),
            "note": "OOS diagnostics (expanding window) for Δ in bps; informational only.",
        }
