from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class HealthResponse(BaseModel):
    ok: bool


class MetaLatestResponse(BaseModel):
    scraped_at_by_url: dict[str, str] = Field(description="Map of source URL to last scraped timestamp")
    latest_scraped_at: Optional[str] = Field(description="Latest scraped timestamp across all sources")
    sources_count: int = Field(description="Total number of sources")
    observations_count: int = Field(description="Total number of observations")
    distinct_days_overall: int = Field(description="Number of distinct calendar days with observations (Phase 2C)")
    last_anomaly: Optional[str] = Field(description="Last anomaly detected, if any", default=None)


class BankResponse(BaseModel):
    bank_name: str


class SeriesResponse(BaseModel):
    code: str
    product_group: str
    description: Optional[str] = None


class LatestRateItem(BaseModel):
    bank_name: str
    series_code: str
    term_months: Optional[int] = None
    term_label: Optional[str] = None
    rate_pct: Optional[float] = None
    rate_min_pct: Optional[float] = None
    rate_max_pct: Optional[float] = None
    raw_value: Optional[str] = None
    scraped_at: str
    source_url: str
    source_priority: Optional[int] = None  # Priority of source (lower = higher priority)


class LatestRatesResponse(BaseModel):
    rows: list[LatestRateItem]
    meta: dict


class HistoryPoint(BaseModel):
    scraped_at: str
    rate_pct: Optional[float] = None
    rate_min_pct: Optional[float] = None
    rate_max_pct: Optional[float] = None


class HistoryResponse(BaseModel):
    points: list[HistoryPoint]
    meta: dict


class ErrorResponse(BaseModel):
    detail: str
