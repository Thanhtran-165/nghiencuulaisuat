"""
Secondary trading normalization helpers.

Goal: provide stable semantic fields for analytics/LLM narration:
- segment_kind / segment_code
- bucket_kind / bucket_code / bucket_display

We keep original `segment` and `bucket_label` as-is for backward compatibility.
"""

from __future__ import annotations

import re
from typing import Optional


SEGMENT_CODE_MAP = {
    # Existing (tests / old UI)
    "Government Bond": ("MARKET_SEGMENT", "GOV_BOND"),
    "T-Bill": ("MARKET_SEGMENT", "T_BILL"),
    "Corporate Bond": ("MARKET_SEGMENT", "CORP_BOND"),
    # HNX trading provider (current ingestion)
    "Outright": ("TRADE_TYPE", "OUTRIGHT"),
    "Repo": ("TRADE_TYPE", "REPO"),
    "SaleAndRepurchase": ("TRADE_TYPE", "SALE_AND_REPURCHASE"),
    "Loan": ("TRADE_TYPE", "LOAN"),
}

INVESTOR_TYPE_CODE_MAP = {
    "Credit Institution": "CREDIT_INSTITUTION",
    "Enterprise": "ENTERPRISE",
    "Individual": "INDIVIDUAL",
    "Foreign": "FOREIGN",
    "Other": "OTHER",
}


def normalize_segment(segment: str) -> tuple[str, str]:
    segment = (segment or "").strip()
    kind_code = SEGMENT_CODE_MAP.get(segment)
    if kind_code:
        return kind_code
    if not segment:
        return ("UNKNOWN", "UNKNOWN")

    code = re.sub(r"[^A-Z0-9]+", "_", segment.upper()).strip("_")
    return ("UNKNOWN", code or "UNKNOWN")


_VN_RANGE_PATTERNS = [
    # Dưới 1 năm
    (re.compile(r"\b(dưới|duoi)\s*(\d+)\s*(năm|nam)\b", re.IGNORECASE), "LT_{a}Y"),
    # Trên 10 năm
    (re.compile(r"\b(trên|tren)\s*(\d+)\s*(năm|nam)\b", re.IGNORECASE), "GT_{a}Y"),
    # Từ 1 đến 3 năm
    (re.compile(r"\b(từ|tu)\s*(\d+)\s*(đến|den)\s*(\d+)\s*(năm|nam)\b", re.IGNORECASE), "Y{a}_{b}"),
    # 1-3 năm / 1 - 3 năm
    (re.compile(r"\b(\d+)\s*[-–]\s*(\d+)\s*(năm|nam)\b", re.IGNORECASE), "Y{a}_{b}"),
]


def _bucket_code_from_vn(text: str) -> Optional[str]:
    t = " ".join((text or "").strip().split())
    for pat, tmpl in _VN_RANGE_PATTERNS:
        m = pat.search(t)
        if not m:
            continue
        nums = [int(x) for x in m.groups() if x and x.isdigit()]
        if not nums:
            continue
        if tmpl.startswith("LT_") or tmpl.startswith("GT_"):
            a = nums[0]
            return tmpl.format(a=a)
        if len(nums) >= 2:
            a, b = nums[0], nums[1]
            lo, hi = min(a, b), max(a, b)
            return tmpl.format(a=lo, b=hi)
    return None


def normalize_bucket(
    bucket_label: str,
    *,
    bucket_context: Optional[str] = None,
) -> tuple[str, str, str]:
    """
    Normalize the bucket label to a stable code + display string.

    bucket_context is a hint about the meaning of the bucket column (e.g. remaining maturity).
    """
    raw = (bucket_label or "").strip()
    if not raw:
        return ("UNKNOWN", "UNKNOWN", "")

    if raw in INVESTOR_TYPE_CODE_MAP:
        code = INVESTOR_TYPE_CODE_MAP[raw]
        return ("INVESTOR_TYPE", code, raw)

    # Vietnamese remaining maturity buckets (common on HNX tables)
    maybe = _bucket_code_from_vn(raw)
    if maybe:
        # Display in compact English for UI/LLM
        if maybe.startswith("LT_"):
            y = maybe.removeprefix("LT_").removesuffix("Y")
            return ("MATURITY_BUCKET", maybe, f"<{y}Y")
        if maybe.startswith("GT_"):
            y = maybe.removeprefix("GT_").removesuffix("Y")
            return ("MATURITY_BUCKET", maybe, f">{y}Y")
        if maybe.startswith("Y") and "_" in maybe:
            span = maybe.removeprefix("Y").replace("_", "-")
            return ("MATURITY_BUCKET", maybe, f"{span}Y")

    # Fallback: context-aware slugs
    kind = "UNKNOWN"
    if bucket_context:
        kind = re.sub(r"[^A-Z0-9]+", "_", bucket_context.upper()).strip("_") or "UNKNOWN"

    code = re.sub(r"[^A-Z0-9]+", "_", raw.upper()).strip("_") or "UNKNOWN"
    return (kind, code, raw)

