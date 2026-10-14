"""Response and request models. The frontend's typed client is generated from these via OpenAPI."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


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
