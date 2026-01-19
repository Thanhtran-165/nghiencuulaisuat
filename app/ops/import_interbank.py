"""
Interbank rate import helpers (CSV -> interbank_rates)

Supports:
- Long format: date,tenor_label,rate[,source]
- Wide format: date,ON,1W,1M,3M,...
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class ImportResult:
    records: list[dict]
    skipped_rows: int


def _parse_iso_date(value: str) -> Optional[date]:
    s = (value or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _normalize_tenor(raw: str) -> str:
    s = re.sub(r"\s+", " ", (raw or "").strip().upper())
    if s in {"O/N", "ON", "OVERNIGHT"}:
        return "ON"
    s = s.replace("MONTHS", "M").replace("MONTH", "M")
    s = s.replace("WEEKS", "W").replace("WEEK", "W")
    s = s.replace("DAYS", "D").replace("DAY", "D")
    s = re.sub(r"[^0-9A-Z]", "", s)
    s = s.replace("MONTH", "M").replace("WEEK", "W").replace("DAY", "D")
    return s


def _parse_rate(value: str) -> Optional[float]:
    s = (value or "").strip()
    if not s:
        return None
    s = re.sub(r"[^0-9,.\-]", "", s)
    if not s or s in {"-", ".", ",", "-.", "-,"}:
        return None
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    if s.count(".") > 1 and s.count(",") == 0:
        s = s.replace(".", "")
    if s.count(",") > 1 and s.count(".") == 0:
        s = s.replace(",", "")
    if "." in s and "," in s:
        if s.rfind(".") > s.rfind(","):
            s = s.replace(",", "")
        else:
            s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_interbank_csv(
    input_path: str | Path,
    *,
    default_source: str = "MANUAL",
    only_tenors: Optional[Iterable[str]] = None,
) -> ImportResult:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    tenor_filter: Optional[set[str]] = None
    if only_tenors:
        tenor_filter = {_normalize_tenor(t) for t in only_tenors if (t or "").strip()}

    records: list[dict] = []
    skipped = 0
    fetched_at = datetime.now().isoformat()

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return ImportResult(records=[], skipped_rows=0)

        header = [h.strip() for h in reader.fieldnames if h]
        header_lower = [h.lower() for h in header]
        has_long = "tenor_label" in header_lower and "rate" in header_lower

        date_key = None
        for k in header:
            if k.lower() in {"date", "ngay", "ngày", "as_of"}:
                date_key = k
                break
        if date_key is None:
            date_key = header[0]

        for row in reader:
            d = _parse_iso_date(row.get(date_key, ""))
            if d is None:
                skipped += 1
                continue

            if has_long:
                tenor = _normalize_tenor(row.get("tenor_label", "") or row.get("Tenor_Label", ""))
                if not tenor:
                    skipped += 1
                    continue
                if tenor_filter is not None and tenor not in tenor_filter:
                    continue
                rate = _parse_rate(row.get("rate", "") or row.get("Rate", ""))
                if rate is None:
                    skipped += 1
                    continue
                source = (row.get("source") or row.get("Source") or default_source).strip() or default_source
                records.append(
                    {
                        "date": d.strftime("%Y-%m-%d"),
                        "tenor_label": tenor,
                        "rate": rate,
                        "source": source,
                        "fetched_at": fetched_at,
                    }
                )
                continue

            for k, v in row.items():
                if k is None:
                    continue
                if k == date_key:
                    continue
                tenor = _normalize_tenor(k)
                if not tenor:
                    continue
                if tenor_filter is not None and tenor not in tenor_filter:
                    continue
                rate = _parse_rate(v)
                if rate is None:
                    continue
                records.append(
                    {
                        "date": d.strftime("%Y-%m-%d"),
                        "tenor_label": tenor,
                        "rate": rate,
                        "source": default_source,
                        "fetched_at": fetched_at,
                    }
                )

    return ImportResult(records=records, skipped_rows=skipped)

