from datetime import date, timedelta

import numpy as np
import pandas as pd

AS_OF = date(2026, 10, 13)


def daily(days: int = 120, base: float = 100.0, noise: float = 0.05, seed: int = 1, end: date = AS_OF,
          mult: dict[int, float] | None = None, from_offset: dict[int, float] | None = None) -> pd.Series:
    """Daily series ending at `end`. mult: {offset: m} single days; from_offset: {offset: m} from that day on."""
    idx = pd.date_range(end - timedelta(days=days - 1), end, freq="D")
    rng = np.random.default_rng(seed)
    v = base * (1 + rng.normal(0, noise, len(idx)))
    off = (idx - pd.Timestamp(end)).days.to_numpy()
    for o, m in (from_offset or {}).items():
        v[off >= o] *= m
    for o, m in (mult or {}).items():
        v[off == o] *= m
    return pd.Series(v, index=idx)


def trading(days: int = 120, base: float = 50.0, end: date = AS_OF, drift_last: tuple[int, float] | None = None,
            seed: int = 2, vol: float = 0.0, volume_boost_last: int = 0) -> tuple[pd.Series, pd.Series]:
    idx = pd.bdate_range(end - timedelta(days=days * 1.5), end)[-days:]
    rng = np.random.default_rng(seed)
    r = rng.normal(0, vol, len(idx))
    if drift_last:
        n, total = drift_last
        r[-n:] += np.log1p(total) / n
    close = pd.Series(base * np.exp(np.cumsum(r)), index=idx)
    volume = pd.Series(1e6 * np.ones(len(idx)), index=idx)
    if volume_boost_last:
        volume.iloc[-volume_boost_last:] *= 2.0
    return close, volume
