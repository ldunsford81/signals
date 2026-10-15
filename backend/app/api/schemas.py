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


# ---- replay, evaluation and the alert log ----------------------------------------------
class ReplayIn(BaseModel):
    start: date | None = None
    end: date | None = None


class HorizonStats(BaseModel):
    n: int
    hits: int
    hit_rate: float | None
    median_excess: float | None
    mean_excess: float | None
    judged: bool


class PerformanceGroup(BaseModel):
    stage: str
    config_hash: str
    trigger: str
    n_alerts: int
    n_counted: int
    hit_rule: str
    headline_horizon: str | None
    first_as_of: date
    last_as_of: date
    horizons: dict[str, HorizonStats]


class PerformanceOut(BaseModel):
    horizons: list[str]
    min_sample_to_judge: int
    dedupe_days: int
    combine_triggers: bool
    current_config_hash: str
    groups: list[PerformanceGroup]


class Outcome(BaseModel):
    stock_return: float | None
    benchmark_return: float | None
    excess_return: float | None
    complete: bool
    computed_at: datetime | None = None


class AlertLogRow(BaseModel):
    id: int
    as_of: date
    stage: str
    prior_stage: str | None
    product_id: int
    product: str
    company: str
    ticker: str
    trigger: str
    config_hash: str
    summary: str
    changed_fields: list[dict[str, Any]]
    counted: bool
    rescaled_history: bool
    decision: str
    outcomes: dict[str, Outcome]


class AlertLogOut(BaseModel):
    total: int
    items: list[AlertLogRow]
    horizons: list[str]
    config_hashes: list[str]


class AlertDetailOut(BaseModel):
    id: int
    as_of: date
    stage: str
    prior_stage: str | None
    trigger: str
    scan_id: int
    product_id: int
    company_id: int
    summary: str
    changed_fields: list[dict[str, Any]]
    config_hash: str
    created_at: datetime
    input_snapshot: dict[str, Any]
    outcomes: dict[str, Outcome]


# ---- operator views: dashboard and ticker page ---------------------------------------
class Segment(BaseModel):
    text: str
    strong: bool = False


class TickerRow(BaseModel):
    ticker: str
    company: str
    short_name: str
    company_id: int
    is_demo: bool
    product_id: int
    product: str
    stage: str
    label: str
    side: str | None
    attention: str
    buzz_ratio: float | None
    buzz_days: int | None
    sources_ok: int
    sources_total: int
    strength: float | None
    price: str
    relative_return: float | None
    volume_ratio: float | None
    benchmark: str
    retail: str
    days_to_earnings: int | None
    earnings_status: str
    earnings_projected: bool
    quarter_closed: bool
    single_source: bool
    new_today: bool
    unknown_reasons: list[str]
    buzz_spark: list[float | None] = []
    price_spark: list[float | None] = []
    products_in_signal: int = 0


class RadarRow(TickerRow):
    kind: str
    note: str


class KpiCount(BaseModel):
    count: int
    new: int
    attention_needed: int | None = None


class HealthIssue(BaseModel):
    source: str
    message: str


class HealthSummary(BaseModel):
    ok: bool
    issues: list[HealthIssue]


class DashScan(BaseModel):
    id: int
    as_of: date
    finished_at: datetime | None
    config_hash: str


class DashboardOut(BaseModel):
    scan: DashScan | None
    headline: list[Segment]
    kpis: dict[str, KpiCount]
    buy: list[TickerRow]
    sell: list[TickerRow]
    radar: list[RadarRow]
    board: list[TickerRow]
    health: HealthSummary


class ProductChoice(BaseModel):
    id: int
    name: str
    stage: str
    label: str
    strength: float | None


class Check(BaseModel):
    label: str
    ok: bool


class SignalSummary(BaseModel):
    stage: str
    label: str
    side: str | None
    since: date | None
    signal_start_date: date | None
    verdict: str
    checks: list[Check]


class ChartPoint(BaseModel):
    date: date
    value: float | None
    low: float | None = None
    high: float | None = None


class TickerChart(BaseModel):
    buzz_source: str | None
    buzz: list[ChartPoint]
    price_rel: list[ChartPoint]
    benchmark: str
    early_move: float
    clear_acceleration: float
    window_start: date | None


class Decision(BaseModel):
    alert_id: int | None
    alert_as_of: date | None
    decision: str
    note: str | None
    reviewed_at: datetime | None


class TickerOut(BaseModel):
    company: CompanyInfo
    products: list[ProductChoice]
    product: ProductInfo
    scan: DetailScan | None
    announcements: list[AnnouncementOut]
    history: list[HistoryRow]
    signal: SignalSummary | None
    tiles: dict[str, dict[str, Any]] | None = None
    earnings: dict[str, Any] | None = None
    decision: Decision | None = None
    chart: TickerChart | None = None
    detail: ProductDetailOut
