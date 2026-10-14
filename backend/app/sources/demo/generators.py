"""Deterministic synthetic series for every demo source.

Every series is generated once over a fixed range around the anchor date with a fixed random
seed per entity, then sliced. The same (anchor, seed) always gives the same numbers, whatever
window a fetch asks for, so re-ingesting is idempotent. Dates after the anchor continue in the
regime the anchor day was in.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd

from app.core import calendar
from app.sources.demo.universe import BENCHMARKS, BY_TICKER, Bump, CompanySpec, ProductSpec

PAST_MARGIN = 30
FUTURE_DAYS = 400


@dataclass(frozen=True)
class World:
    anchor: date
    history_days: int
    seed: int

    @property
    def first_day(self) -> date:
        return self.anchor - timedelta(days=self.history_days + PAST_MARGIN)

    @property
    def last_day(self) -> date:
        return self.anchor + timedelta(days=FUTURE_DAYS)

    def days(self) -> pd.DatetimeIndex:
        return pd.date_range(self.first_day, self.last_day, freq="D")

    def offsets(self, idx: pd.DatetimeIndex) -> np.ndarray:
        return (idx - pd.Timestamp(self.anchor)).days.to_numpy()

    def rng(self, *key: str) -> np.random.Generator:
        return np.random.default_rng([self.seed, zlib.crc32("|".join(key).encode())])


# ---- multipliers --------------------------------------------------------
def bump_multiplier(b: Bump, off: np.ndarray) -> np.ndarray:
    m = np.ones(len(off))
    if b.kind == "spike":
        m[off == b.start] = b.mult
        return m
    end = b.end if b.end is not None else 10**6
    if b.kind == "step":
        ramp = np.clip((off - b.start + 1) / 2.0, 0, 1)
        active = (off >= b.start) & (off <= end)
        m = np.where(active, 1 + (b.mult - 1) * ramp, 1.0)
    elif b.kind == "exp":
        span = max(-b.start, 1)
        k = np.log(b.mult) / span
        t = np.clip(off - b.start, 0, span)
        m = np.where(off >= b.start, np.exp(k * t), 1.0)
    elif b.kind == "episode":
        up_end = b.start + 7
        hold_end = up_end + b.hold
        down_end = hold_end + 10
        m = np.ones(len(off))
        up = (off >= b.start) & (off < up_end)
        m[up] = 1 + (b.mult - 1) * (off[up] - b.start + 1) / 7
        m[(off >= up_end) & (off < hold_end)] = b.mult
        down = (off >= hold_end) & (off < down_end)
        m[down] = b.mult - (b.mult - 1) * (off[down] - hold_end + 1) / 10
    else:
        raise ValueError(f"unknown bump kind {b.kind}")
    return m


def combined(bumps, off: np.ndarray, source: str, unique: bool = False) -> np.ndarray:
    m = np.ones(len(off))
    for b in bumps:
        if source in b.sources:
            if unique and b.unique_mult is not None:
                b = Bump(b.start, b.kind, b.unique_mult, b.end, b.hold, b.sources)
            m *= bump_multiplier(b, off)
    return m


def generic_product(ticker: str, name: str) -> ProductSpec:
    """A product added by hand (Admin or CSV) in demo mode: rising attention from 12 days before the
    anchor, so it visibly flows through ingest, scan and alerts. Clearly synthetic, like all demo data."""
    return ProductSpec(name=name, keywords=(name.lower(),), bumps=(Bump(-12, "step", 2.6),),
                       scenario="added by hand: synthetic rising attention")


def generic_company(ticker: str) -> CompanySpec:
    return CompanySpec(ticker, ticker, "unknown", "XLY", 1000, 5, ())


# ---- product attention --------------------------------------------------
@lru_cache(maxsize=256)
def product_raw(world: World, ticker: str, product_name: str) -> pd.DataFrame:
    """Raw (un-rescaled) search level, social mentions and posts for one product."""
    comp = BY_TICKER.get(ticker)
    spec = next((p for p in comp.products if p.name == product_name), None) if comp else None
    spec = spec or generic_product(ticker, product_name)
    idx = world.days()
    off = world.offsets(idx)
    rng = world.rng("product", ticker, product_name)
    search = spec.base_search * combined(spec.bumps, off, "search") * (1 + rng.normal(0, 0.06, len(idx)))
    lam = spec.base_social * combined(spec.bumps, off, "social")
    mentions = rng.poisson(lam).astype(float)
    posts = rng.binomial(mentions.astype(int), 0.3).astype(float)
    df = pd.DataFrame({"search": np.clip(search, 0.1, None), "mentions": mentions, "posts": posts}, index=idx)
    if spec.social_ends is not None:
        df.loc[off > spec.social_ends, ["mentions", "posts"]] = np.nan
    return df


def rescale_window(raw: pd.Series, start: date, end: date) -> pd.Series:
    """Google-Trends style: 0–100 relative to the max inside the pulled window, integers."""
    w = raw.loc[pd.Timestamp(start):pd.Timestamp(end)]
    if w.empty or w.max() <= 0:
        return w
    return (100 * w / w.max()).round()


# ---- prices ---------------------------------------------------------------
@lru_cache(maxsize=8)
def _sessions(world: World) -> pd.DatetimeIndex:
    return pd.DatetimeIndex([pd.Timestamp(d) for d in calendar.sessions_between(world.first_day, world.last_day)])


@lru_cache(maxsize=16)
def benchmark_prices(world: World, ticker: str) -> pd.DataFrame:
    idx = _sessions(world)
    rng = world.rng("benchmark", ticker)
    rets = rng.normal(0.0003, 0.009, len(idx))
    close = BENCHMARKS.get(ticker, 100.0) * np.exp(np.cumsum(rets))
    volume = 20_000_000 * np.exp(rng.normal(0, 0.15, len(idx)))
    return pd.DataFrame({"close": close, "volume": volume}, index=idx)


@lru_cache(maxsize=64)
def company_prices(world: World, ticker: str) -> pd.DataFrame:
    spec = BY_TICKER.get(ticker) or generic_company(ticker)
    idx = _sessions(world)
    off = world.offsets(idx)
    rng = world.rng("price", ticker)
    idio = rng.normal(0, 0.006, len(idx))
    vol_noise = np.exp(rng.normal(0, 0.18, len(idx)))
    calm_noise = rng.normal(0, 0.0015, len(idx))
    volume_mult = np.ones(len(idx))
    for mv in spec.price_moves:
        win = (off >= mv.start) & (off <= mv.end)
        if not win.any():
            continue
        if mv.calm:
            idio[win] = calm_noise[win]
        n = win.sum()
        idio[win] += (np.log1p(mv.rel) - idio[win].sum()) / n
        vfrom = mv.volume_from if mv.volume_from is not None else mv.start
        volume_mult[(off >= vfrom) & (off <= mv.end)] *= mv.volume_mult
    # continuation after anchor: no idiosyncratic drift
    idio[off > 0] = calm_noise[off > 0]
    bench = benchmark_prices(world, spec.benchmark)["close"].to_numpy()
    close = spec.base_price * (bench / bench[0]) * np.exp(np.cumsum(idio))
    volume = spec.base_volume * vol_noise * volume_mult
    df = pd.DataFrame({"close": close.round(4), "volume": volume.round()}, index=idx)
    if spec.price_ends is not None:
        df = df.loc[off <= spec.price_ends]
    return df


# ---- retail interest ------------------------------------------------------
@lru_cache(maxsize=64)
def company_retail(world: World, ticker: str) -> pd.DataFrame:
    spec = BY_TICKER.get(ticker) or generic_company(ticker)
    idx = world.days()
    off = world.offsets(idx)
    rng = world.rng("retail", ticker)
    ts = spec.base_ticker_search * combined(spec.retail_bumps, off, "ticker_search") * (1 + rng.normal(0, 0.05, len(idx)))
    count_lam = spec.base_cashtag * combined(spec.retail_bumps, off, "cashtag")
    uniq_lam = spec.base_cashtag * 0.55 * combined(spec.retail_bumps, off, "cashtag", unique=True)
    counts = rng.poisson(count_lam).astype(float)
    uniq = np.minimum(rng.poisson(uniq_lam), counts).astype(float)
    return pd.DataFrame({"ticker_search": np.clip(ts, 0.1, None), "mention_count": counts,
                         "unique_accounts": uniq}, index=idx)


# ---- earnings calendar ----------------------------------------------------
@lru_cache(maxsize=64)
def company_earnings(world: World, ticker: str) -> pd.DataFrame:
    """Point-in-time view of the earnings calendar: what the source reported on each day."""
    spec = BY_TICKER.get(ticker) or generic_company(ticker)
    idx = world.days()
    first = world.anchor + timedelta(days=spec.earnings_in_days)
    # Quarterly cadence; when the next print is more than a quarter away, the previous one was recent.
    prev = first - timedelta(days=max(91, spec.earnings_in_days + 1))
    schedule = [first + timedelta(days=91 * k) for k in range(8)] + [prev - timedelta(days=91 * k) for k in range(8)]
    rows = []
    stale_cut = world.anchor + timedelta(days=spec.earnings_stale_from) if spec.earnings_stale_from is not None else None
    frozen = None
    for ts in idx:
        d = ts.date()
        if stale_cut is not None and d > stale_cut:
            rows.append(frozen)
            continue
        nxt = min(s for s in schedule if s >= d)
        row = (nxt, (nxt - d).days <= 30, nxt - timedelta(days=spec.quarter_lag))
        rows.append(row)
        frozen = row
    return pd.DataFrame(rows, index=idx, columns=["next_earnings_date", "confirmed", "fiscal_quarter_end"])
