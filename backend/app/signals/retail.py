"""Retail interest (per company): quiet | rising | elevated | unknown.

Per healthy retail source: last 3 days vs baseline (days 4–30).
rising if ratio >= 1.5 or z >= 2.0; elevated if ratio >= 3.0 and z >= 3.0.
A source with a breadth metric (cashtag unique accounts) reaches elevated only when breadth is
also up >= 1.3x; names outside the post sample can reach rising only.
Family status = highest level among healthy sources.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from app.core.config import Settings
from app.signals.health import assess, num, window_stats
from app.signals.store import SeriesInfo

LEVELS = ["quiet", "rising", "elevated"]


@dataclass
class RetailInput:
    source: str
    metric: str
    series: pd.Series
    info: SeriesInfo = field(default_factory=SeriesInfo)
    sparse_floor: bool = False
    breadth_metric: str | None = None
    breadth: pd.Series | None = None


@dataclass
class RetailResult:
    status: str
    components: dict


def _today(st: pd.DataFrame, as_of: date) -> pd.Series | None:
    ts = pd.Timestamp(as_of)
    return st.loc[ts] if ts in st.index else None


def compute_retail(inputs: list[RetailInput], as_of: date, settings: Settings) -> RetailResult:
    cfg = settings.retail
    min_hist = settings.health.min_history_days["retail"]
    sources: dict[str, dict] = {}
    best, set_by = -1, None
    for inp in inputs:
        st = window_stats(inp.series, as_of, cfg.short_window, tuple(cfg.baseline_window))
        today = _today(st, as_of)
        bm = None if today is None or pd.isna(today["base_mean"]) else float(today["base_mean"])
        h = assess(inp.series, as_of, settings.staleness(inp.source), min_hist,
                   settings.health.min_baseline_index if inp.sparse_floor else None, bm)
        comp = {"source": inp.source, "metric": inp.metric, **h, "rescaled_history": inp.info.rescaled_history}
        if today is not None:
            comp.update(ratio=num(today["ratio"]), z=num(today["z"]), short_mean=num(today["short_mean"]),
                        baseline_mean=num(today["base_mean"]))
        if h["healthy"] and today is not None:
            ratio = today["ratio"] if pd.notna(today["ratio"]) else 0.0
            z = today["z"] if pd.notna(today["z"]) else 0.0
            level = 0
            if ratio >= cfg.elevated.min_ratio and z >= cfg.elevated.min_z:
                level = 2
            elif ratio >= cfg.rising.min_ratio or z >= cfg.rising.min_z:
                level = 1
            if level == 2 and inp.breadth_metric:
                level, note = _breadth_check(inp, as_of, settings)
                comp["breadth"] = note
            comp["level"] = LEVELS[level]
            if level > best:
                best, set_by = level, inp.source
        sources[inp.source] = comp

    components: dict = {"sources": sources, "set_by": set_by}
    if best < 0:
        components["reason"] = "no healthy retail source: " + "; ".join(
            f"{k}: {v['reason'] or 'no data on as_of'}" for k, v in sources.items()) if sources else "no retail sources"
        return RetailResult("unknown", components)
    return RetailResult(LEVELS[best], components)


def _breadth_check(inp: RetailInput, as_of: date, settings: Settings) -> tuple[int, dict]:
    cfg = settings.retail
    b = inp.breadth if inp.breadth is not None else pd.Series(dtype=float)
    h = assess(b, as_of, settings.staleness(inp.source), settings.health.min_history_days["retail"])
    if not h["healthy"]:
        return 1, {"metric": inp.breadth_metric, "result": "outside_sample",
                   "reason": f"{inp.breadth_metric}: {h['reason']}; capped at rising"}
    st = window_stats(b, as_of, cfg.short_window, tuple(cfg.baseline_window))
    today = _today(st, as_of)
    ratio = float(today["ratio"]) if today is not None and pd.notna(today["ratio"]) else 0.0
    ok = ratio >= cfg.cashtag_min_unique_account_ratio
    return (2 if ok else 1), {"metric": inp.breadth_metric, "ratio": num(ratio),
                              "min_ratio": cfg.cashtag_min_unique_account_ratio,
                              "result": "passed" if ok else "too_few_accounts"}
