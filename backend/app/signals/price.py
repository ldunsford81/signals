"""Price response (per product): flat | early_move | clear_acceleration | unknown.

Anchored at the product's signal_start_date (or a 20-trading-day lookback, `no_anchor`).
relative_return = stock return - benchmark return over the anchor period.
volume_ratio = mean volume last 5 sessions / mean volume last 60 sessions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.core.config import Settings
from app.signals.health import assess, num


@dataclass
class PriceResult:
    status: str
    components: dict


def compute_price(close: pd.Series, volume: pd.Series, bench_close: pd.Series, benchmark: str, as_of: date,
                  anchor: date | None, settings: Settings) -> PriceResult:
    cfg = settings.price_response
    stale, hist = settings.staleness("price"), settings.health.min_history_days["price"]
    h_stock = assess(close, as_of, stale, hist)
    h_bench = assess(bench_close, as_of, stale, hist)
    comp: dict = {"benchmark": benchmark, "health": {"stock": h_stock, "benchmark": h_bench}}
    if not h_stock["healthy"] or not h_bench["healthy"]:
        bad = [f"{n}: {h['reason']}" for n, h in (("price", h_stock), (benchmark, h_bench)) if not h["healthy"]]
        comp["reason"] = "; ".join(bad)
        return PriceResult("unknown", comp)

    if anchor is not None:
        before = close.loc[:pd.Timestamp(anchor) - pd.Timedelta(days=1)]
        if before.empty:
            before = close.iloc[:1]
        base_ts = before.index[-1]
        comp["anchor_label"] = "signal_start"
        comp["anchor_date"] = anchor.isoformat()
    else:
        n = cfg.no_signal_lookback_days
        base_ts = close.index[-(n + 1)] if len(close) > n else close.index[0]
        comp["anchor_label"] = "no_anchor"
        comp["anchor_date"] = None
    base_stock = float(close.loc[base_ts])
    last_stock = float(close.iloc[-1])
    bench_base = bench_close.loc[:base_ts]
    if bench_base.empty:
        comp["reason"] = f"{benchmark}: no benchmark price at {base_ts.date()}"
        return PriceResult("unknown", comp)
    stock_ret = last_stock / base_stock - 1
    bench_ret = float(bench_close.iloc[-1]) / float(bench_base.iloc[-1]) - 1
    rel = stock_ret - bench_ret

    short_w, long_w = cfg.volume_ratio_windows
    vol_ratio = None
    if len(volume) >= long_w:
        long_mean = volume.iloc[-long_w:].mean()
        if long_mean > 0:
            vol_ratio = float(volume.iloc[-short_w:].mean() / long_mean)

    ca, em = cfg.clear_acceleration, cfg.early_move
    vr = vol_ratio if vol_ratio is not None else 0.0
    if rel >= ca.min_relative_return and vr >= ca.min_volume_ratio:
        status = "clear_acceleration"
    elif rel >= em.min_relative_return or vr >= em.min_volume_ratio:
        status = "early_move"
    else:
        status = "flat"
    comp.update(base_date=base_ts.date().isoformat(), stock_return=num(stock_ret), benchmark_return=num(bench_ret),
                relative_return=num(rel), volume_ratio=num(vol_ratio), last_close=num(last_stock),
                volume_history_ok=vol_ratio is not None)
    return PriceResult(status, comp)
