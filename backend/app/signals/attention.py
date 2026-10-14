"""Product attention: elevated | normal | seasonal | unknown.

1. Per healthy source: short window (last 7 days) vs baseline (days 8–56): ratio and z.
2. A source is accelerating on a day when ratio >= 1.5 and z >= 2.0.
3. Elevated when >= min_accelerating_sources healthy sources are accelerating on >= 4 of the
   last 5 days (one is enough if only one source is healthy: `single_source`).
4. Seasonality: with >= 365 days of history, a year-over-year ratio below 1.2 makes it seasonal.
5. signal_start_date: first day of the current unbroken elevated run (last 90 days).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.core.config import Settings
from app.signals.health import assess, num, window_stats
from app.signals.store import SeriesInfo


@dataclass
class SourceInput:
    source: str
    metric: str
    series: pd.Series
    info: SeriesInfo = field(default_factory=SeriesInfo)
    sparse_floor: bool = False


@dataclass
class AttentionResult:
    status: str
    score: float | None
    signal_start_date: date | None
    last_elevated_date: date | None
    single_source: bool
    n_healthy: int
    n_accelerating: int
    components: dict


def compute_attention(inputs: list[SourceInput], as_of: date, settings: Settings) -> AttentionResult:
    cfg = settings.attention
    ts = pd.Timestamp(as_of)
    lookback_start = ts - pd.Timedelta(days=cfg.signal_lookback_days - 1)
    sources: dict[str, dict] = {}
    persistent: dict[str, pd.Series] = {}
    stats: dict[str, pd.DataFrame] = {}

    for inp in inputs:
        st = window_stats(inp.series, as_of, cfg.short_window, tuple(cfg.baseline_window))
        today = st.loc[ts] if ts in st.index else None
        base_mean = today["base_mean"] if today is not None else None
        h = assess(inp.series, as_of, settings.staleness(inp.source), settings.health.min_history_days["attention"],
                   settings.health.min_baseline_index if inp.sparse_floor else None,
                   None if base_mean is None or pd.isna(base_mean) else float(base_mean))
        comp = {"source": inp.source, "metric": inp.metric, **h,
                "rescaled_history": inp.info.rescaled_history, "snapshot_id": inp.info.snapshot_id}
        if today is not None:
            comp.update(ratio=num(today["ratio"]), z=num(today["z"]), short_mean=num(today["short_mean"]),
                        baseline_mean=num(today["base_mean"]), baseline_std=num(today["base_std"]))
        if h["healthy"] and not st.empty:
            acc = ((st["ratio"] >= cfg.accelerating.min_ratio) & (st["z"] >= cfg.accelerating.min_z)).astype(int)
            pers = acc.rolling(cfg.persistence.of_last, min_periods=1).sum() >= cfg.persistence.days_required
            comp["accelerating_days"] = int(acc.iloc[-cfg.persistence.of_last:].sum())
            comp["accelerating_today"] = bool(acc.iloc[-1])
            comp["persistent"] = bool(pers.iloc[-1])
            persistent[inp.source] = pers
            stats[inp.source] = st
        sources[inp.source] = comp

    n_healthy = len(persistent)
    components: dict = {"sources": sources, "n_healthy": n_healthy}
    if n_healthy == 0:
        components["reason"] = "no healthy attention source: " + "; ".join(
            f"{k}: {v['reason']}" for k, v in sources.items()) if sources else "no attention sources configured"
        return AttentionResult("unknown", None, None, None, False, 0, 0, components)

    single = n_healthy == 1
    needed = 1 if (single and cfg.allow_single_source_when_only_one_healthy) else cfg.min_accelerating_sources
    grid = pd.date_range(lookback_start, ts, freq="D")
    count = sum(p.reindex(grid, fill_value=False).astype(int) for p in persistent.values())
    elevated = count >= needed
    elevated_now = bool(elevated.iloc[-1])
    accelerating_now = [k for k, p in persistent.items() if bool(p.iloc[-1])]
    zs = [sources[k].get("z") for k in accelerating_now if sources[k].get("z") is not None]
    score = float(np.mean(zs)) if zs else None

    run_start = None
    if elevated_now:
        i = len(elevated) - 1
        while i > 0 and elevated.iloc[i - 1]:
            i -= 1
        run_start = elevated.index[i].date()
        components["run_capped_at_lookback"] = i == 0
    true_days = elevated[elevated]
    last_elevated = true_days.index[-1].date() if len(true_days) else None
    components.update(needed_sources=needed, single_source=single, accelerating_sources=accelerating_now,
                      elevated_days_in_lookback=int(elevated.sum()))

    status = "elevated" if elevated_now else "normal"
    if elevated_now:
        season = seasonality(stats, accelerating_now, as_of, settings)
        components["seasonality"] = season
        if season["result"] == "seasonal":
            status = "seasonal"
            before = elevated.loc[:pd.Timestamp(run_start) - pd.Timedelta(days=1)]
            prior = before[before]
            last_elevated = prior.index[-1].date() if len(prior) else None
            components["seasonal_run_start"] = run_start.isoformat()
            run_start = None
    else:
        components["seasonality"] = {"result": "not_checked"}
    return AttentionResult(status, num(score), run_start, last_elevated, single, n_healthy,
                           len(accelerating_now), components)


def seasonality(stats: dict[str, pd.DataFrame], sources: list[str], as_of: date, settings: Settings) -> dict:
    cfg = settings.attention.seasonality
    year_ago = pd.Timestamp(as_of - timedelta(days=365))
    yoy: dict[str, float] = {}
    for src in sources:
        st = stats[src]
        if st.empty or (pd.Timestamp(as_of) - st.index[0]).days + 1 < cfg.min_history_days or year_ago not in st.index:
            continue
        then, now = st.loc[year_ago, "short_mean"], st.iloc[-1]["short_mean"]
        if pd.notna(then) and then > 0 and pd.notna(now):
            yoy[src] = round(float(now / then), 3)
    if not yoy:
        return {"result": "insufficient_history", "yoy_ratio": {}}
    med = float(np.median(list(yoy.values())))
    return {"result": "seasonal" if med < cfg.min_yoy_ratio else "passed", "yoy_ratio": yoy,
            "median_yoy": round(med, 3), "min_yoy_ratio": cfg.min_yoy_ratio}
