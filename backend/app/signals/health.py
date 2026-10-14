"""Input health: is a series fresh enough, long enough and (for 0–100 indexes) dense enough to use?"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd


def window_stats(series: pd.Series, as_of: date, short: int, baseline: tuple[int, int]) -> pd.DataFrame:
    """Daily rolling stats on a calendar-day grid ending at as_of.

    short_mean: mean of days 1..short (day 1 = the date itself).
    baseline:   days lo..hi before it (e.g. 8..56), mean and sample std.
    """
    if series.empty:
        return pd.DataFrame(columns=["value", "short_mean", "base_mean", "base_std", "ratio", "z"])
    idx = pd.date_range(series.index.min(), pd.Timestamp(as_of), freq="D")
    s = series.reindex(idx)
    lo, hi = baseline
    width = hi - lo + 1
    short_mean = s.rolling(short, min_periods=max(1, short // 2 + 1)).mean()
    base = s.shift(lo - 1).rolling(width, min_periods=max(2, width // 2))
    base_mean, base_std = base.mean(), base.std()
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = (short_mean / base_mean).where(base_mean > 0)
        diff = short_mean - base_mean
        z = (diff / base_std).where(base_std > 0)
        z = z.where(base_std > 0, np.where(diff > 0, np.inf, 0.0))
        z = z.where(base_mean.notna())
    return pd.DataFrame({"value": s, "short_mean": short_mean, "base_mean": base_mean, "base_std": base_std,
                         "ratio": ratio, "z": z})


def assess(series: pd.Series, as_of: date, max_staleness_days: int, min_history_days: int,
           min_baseline_index: float | None = None, baseline_mean: float | None = None) -> dict:
    """Return {healthy, reason, last_obs_date, history_days}. `reason` is None when healthy."""
    if series.empty:
        return {"healthy": False, "reason": "no data", "last_obs_date": None, "history_days": 0}
    last = series.index[-1].date()
    first = series.index[0].date()
    history = (as_of - first).days + 1
    out = {"healthy": True, "reason": None, "last_obs_date": last.isoformat(), "history_days": history}
    stale = (as_of - last).days
    if stale > max_staleness_days:
        out.update(healthy=False, reason=f"stale: last observation {last} is {stale}d old (limit {max_staleness_days}d)")
    elif history < min_history_days:
        out.update(healthy=False, reason=f"insufficient history: {history}d < {min_history_days}d")
    elif min_baseline_index is not None and baseline_mean is not None and baseline_mean < min_baseline_index:
        out.update(healthy=False, reason=f"too_sparse: baseline mean {baseline_mean:.1f} < {min_baseline_index:g}")
    return out


def num(x) -> float | None:
    """JSON-safe float (None for NaN, rounded)."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if np.isnan(f):
        return None
    if np.isinf(f):
        return 999.0 if f > 0 else -999.0
    return round(f, 4)
