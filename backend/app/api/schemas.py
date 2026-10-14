"""Response and request models. The frontend's typed client is generated from these via OpenAPI."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ScanInfo(BaseModel):
    id: int
    as_of: date
    trigger: str
    config_hash: str
    started_at: datetime
    finished_at: datetime | None
    status: str


class SourceStatus(BaseModel):
    source: str
    mode: str
    scope: str | None
    last_run_status: str | None
    last_run_at: datetime | None
    rows_written: int | None
    last_good_obs_date: date | None
    error_message: str | None
    stale: bool
    staleness_limit_days: int | None


class StatusOut(BaseModel):
    as_of: date | None
    latest_scan: ScanInfo | None
    config_hash: str
    demo_mode: bool
    demo_anchor_date: date | None
    warnings: list[str]
    sources: list[SourceStatus]


class Badge(BaseModel):
    status: str
    reason: str | None = None


class AttentionBadge(Badge):
    score: float | None = None
    single_source: bool = False
    seasonal: bool = False


class PriceBadge(Badge):
    relative_return: float | None = None
    volume_ratio: float | None = None
    benchmark: str | None = None


class RetailBadge(Badge):
    set_by: str | None = None


class WatchlistRow(BaseModel):
    product_id: int
    product: str
    company_id: int
    company: str
    ticker: str
    is_demo: bool
    stage: str
    attention: AttentionBadge
    price: PriceBadge
    retail: RetailBadge
    signal_start_date: date | None
    days_to_earnings: int | None
    next_earnings_date: date | None
    earnings_projected: bool
    earnings_status: str
    earnings_reason: str | None
    days_left_in_quarter: int | None
    quarter_closed: bool
    rescaled_history: bool


class WatchlistOut(BaseModel):
    scan: ScanInfo | None
    earnings_window_days: tuple[int, int]
    stage_order: list[str]
    total: int
    rows: list[WatchlistRow]


class RunRequest(BaseModel):
    as_of: date | None = None
    sources: list[str] | None = None


class JobOut(BaseModel):
    ok: bool
    result: dict[str, Any] | None = None
    error: str | None = None


# ---- product detail ---------------------------------------------------------
class BandPoint(BaseModel):
    date: date
    value: float | None
    short_mean: float | None
    baseline_mean: float | None
    band_low: float | None
    band_high: float | None
    ratio: float | None
    z: float | None
    breadth_value: float | None = None
    breadth_short_mean: float | None = None


class SourceSeries(BaseModel):
    source: str
    metric: str
    short_window: int
    rescaled_history: bool
    breadth_metric: str | None = None
    points: list[BandPoint]


class PricePoint(BaseModel):
    date: date
    close: float | None
    volume: float | None
    benchmark_rebased: float | None


class AnnouncementOut(BaseModel):
    id: int
    event_date: date
    type: str
    title: str
    url: str | None
    product_id: int | None


class HistoryRow(BaseModel):
    scan_id: int
    as_of: date
    trigger: str
    config_hash: str
    stage: str
    attention: str
    price: str
    retail: str
    days_to_earnings: int | None


class AlertRow(BaseModel):
    id: int
    as_of: date
    stage: str
    prior_stage: str | None
    changed_fields: list[dict[str, Any]]
    summary: str
    config_hash: str
    trigger: str
    created_at: datetime


class ProductInfo(BaseModel):
    id: int
    name: str
    keywords: list[str]
    launched_on: date | None
    active: bool


class CompanyInfo(BaseModel):
    id: int
    ticker: str
    name: str
    sector: str | None
    benchmark: str
    market_cap_usd_m: float | None
    analyst_count: int | None
    is_demo: bool


class DetailScan(BaseModel):
    id: int
    as_of: date
    trigger: str
    config_hash: str
    finished_at: datetime | None


class DetailState(BaseModel):
    stage: str
    attention_status: str
    attention_score: float | None
    attention_components: dict[str, Any]
    price_response: str
    price_components: dict[str, Any]
    retail_status: str
    retail_components: dict[str, Any]
    signal_start_date: date | None
    days_to_earnings: int | None
    days_left_in_quarter: int | None
    input_health: dict[str, Any]


class ProductDetailOut(BaseModel):
    product: ProductInfo
    company: CompanyInfo
    scan: DetailScan | None
    state: DetailState | None
    window_start: date | None
    attention_series: list[SourceSeries]
    price_series: list[PricePoint]
    benchmark_scale: float | None = None
    benchmark_rebased_on: date | None = None
    retail_series: list[SourceSeries]
    announcements: list[AnnouncementOut]
    history: list[HistoryRow]
    alerts: list[AlertRow]


# ---- review feed --------------------------------------------------------------
class FieldChange(BaseModel):
    field: str
    label: str
    from_: str | None = Field(None, alias="from")
    to: str | None

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class FeedCard(BaseModel):
    product_id: int
    product: str
    company_id: int
    company: str
    ticker: str
    is_demo: bool
    stage: str
    summary: str
    reason: str | None
    attention: str
    attention_score: float | None
    single_source: bool
    price: str
    relative_return: float | None
    volume_ratio: float | None
    benchmark: str | None
    retail: str
    signal_start_date: date | None
    days_to_earnings: int | None
    earnings_projected: bool
    earnings_status: str
    days_left_in_quarter: int | None
    quarter_closed: bool
    is_new: bool
    changes: list[FieldChange]
    alert_id: int | None
    alert_as_of: date | None
    decision: str
    note: str | None
    reviewed_at: datetime | None


class FeedGroup(BaseModel):
    company_id: int
    company: str
    ticker: str
    is_demo: bool
    cards: list[FeedCard]


class UnknownInput(BaseModel):
    family: str
    reason: str


class HealthItem(BaseModel):
    product_id: int
    product: str
    company: str
    ticker: str
    attention: str
    signal_start_date: date | None
    unknown_inputs: list[UnknownInput]
    reason: str | None


class FeedScan(BaseModel):
    id: int
    as_of: date
    trigger: str
    config_hash: str
    finished_at: datetime | None


class FeedOut(BaseModel):
    scan: FeedScan | None
    prior_as_of: date | None
    groups: list[FeedGroup]
    health: list[HealthItem]
    counts: dict[str, int]


class ReviewIn(BaseModel):
    decision: Literal["unreviewed", "acted", "passed", "exited"]
    note: str | None = Field(None, max_length=2000)


class ReviewOut(BaseModel):
    id: int
    alert_id: int
    decision: str
    note: str | None
    reviewed_at: datetime
