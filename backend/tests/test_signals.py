"""One unit test per status rule, on small fixture series."""
from datetime import date, timedelta

import pandas as pd

from app.signals.attention import SourceInput, compute_attention
from app.signals.price import compute_price
from app.signals.retail import RetailInput, compute_retail
from helpers import AS_OF, daily, trading


def att(settings, *series, names=("search_interest", "social_mentions"), sparse=(False, False)):
    inputs = [SourceInput(n, "m", s, sparse_floor=f) for n, s, f in zip(names, series, sparse)]
    return compute_attention(inputs, AS_OF, settings)


# ---- attention ------------------------------------------------------------------
def test_elevated_when_two_sources_accelerate(settings):
    r = att(settings, daily(seed=1, from_offset={-10: 2.5}), daily(seed=2, from_offset={-10: 2.5}))
    assert r.status == "elevated"
    assert not r.single_source
    assert r.n_accelerating == 2
    assert r.signal_start_date is not None and r.signal_start_date <= AS_OF - timedelta(days=5)
    assert r.score and r.score > 2


def test_normal_when_flat(settings):
    r = att(settings, daily(seed=1), daily(seed=2))
    assert r.status == "normal"
    assert r.signal_start_date is None


def test_single_day_spike_is_normal(settings):
    # One source spikes for a day (and keeps a short-window bump); the second source is flat.
    r = att(settings, daily(seed=1, mult={-3: 5.0}), daily(seed=2))
    assert r.status == "normal"


def test_one_source_alone_needs_persistence(settings):
    # Only one source accelerating while two are healthy is not enough.
    r = att(settings, daily(seed=1, from_offset={-10: 2.5}), daily(seed=2))
    assert r.status == "normal"


def test_single_source_when_only_one_healthy(settings):
    stale_social = daily(seed=2, end=AS_OF - timedelta(days=10), from_offset={-1: 2.5})
    r = att(settings, daily(seed=1, from_offset={-10: 2.5}), stale_social)
    assert r.status == "elevated"
    assert r.single_source
    assert r.components["sources"]["social_mentions"]["healthy"] is False
    assert "stale" in r.components["sources"]["social_mentions"]["reason"]


def test_seasonal_when_same_window_last_year(settings):
    def s(seed):
        x = daily(days=420, seed=seed, from_offset={-10: 2.5})
        idx = x.index
        ly = (idx >= pd.Timestamp(AS_OF - timedelta(days=375))) & (idx <= pd.Timestamp(AS_OF - timedelta(days=330)))
        x[ly] *= 2.5
        return x
    r = att(settings, s(1), s(2))
    assert r.status == "seasonal"
    assert r.components["seasonality"]["result"] == "seasonal"
    assert r.signal_start_date is None


def test_insufficient_history_skips_seasonality(settings):
    r = att(settings, daily(seed=1, from_offset={-10: 2.5}), daily(seed=2, from_offset={-10: 2.5}))
    assert r.components["seasonality"]["result"] == "insufficient_history"


def test_too_sparse_search_is_unhealthy(settings):
    sparse = daily(base=3, noise=0.3, seed=1, from_offset={-10: 3.0}).round()
    r = att(settings, sparse, daily(seed=2), sparse=(True, False))
    comp = r.components["sources"]["search_interest"]
    assert comp["healthy"] is False and comp["reason"].startswith("too_sparse")


def test_stale_inputs_make_attention_unknown(settings):
    old = AS_OF - timedelta(days=20)
    r = att(settings, daily(seed=1, end=old), daily(seed=2, end=old))
    assert r.status == "unknown"
    assert "stale" in r.components["reason"]


# ---- price --------------------------------------------------------------------------
def test_price_flat_early_and_clear(settings):
    bench, _ = trading(base=100, seed=9)
    flat_c, flat_v = trading()
    assert compute_price(flat_c, flat_v, bench, "XLY", AS_OF, None, settings).status == "flat"
    early_c, early_v = trading(drift_last=(10, 0.05))
    r = compute_price(early_c, early_v, bench, "XLY", AS_OF, AS_OF - timedelta(days=20), settings)
    assert r.status == "early_move" and r.components["anchor_label"] == "signal_start"
    clear_c, clear_v = trading(drift_last=(10, 0.12), volume_boost_last=5)
    assert compute_price(clear_c, clear_v, bench, "XLY", AS_OF, None, settings).status == "clear_acceleration"
    vol_c, vol_v = trading(volume_boost_last=5)
    assert compute_price(vol_c, vol_v, bench, "XLY", AS_OF, None, settings).status == "early_move"


def test_stale_price_is_unknown(settings):
    bench, _ = trading(base=100, seed=9)
    c, v = trading(end=AS_OF - timedelta(days=6))
    r = compute_price(c, v, bench, "XLY", AS_OF, None, settings)
    assert r.status == "unknown" and "stale" in r.components["reason"]


# ---- retail ---------------------------------------------------------------------------
def test_retail_levels(settings):
    quiet = compute_retail([RetailInput("ticker_search_interest", "i", daily(base=30, seed=3))], AS_OF, settings)
    assert quiet.status == "quiet"
    rising = compute_retail([RetailInput("ticker_search_interest", "i", daily(base=30, seed=3, from_offset={-2: 1.8}))],
                            AS_OF, settings)
    assert rising.status == "rising"
    elevated = compute_retail([RetailInput("ticker_search_interest", "i", daily(base=30, seed=3, from_offset={-2: 4}))],
                              AS_OF, settings)
    assert elevated.status == "elevated"


def test_cashtag_burst_from_few_accounts_stays_rising(settings):
    counts = daily(base=30, seed=4, from_offset={-2: 4.0})
    few = daily(base=16, seed=5, from_offset={-2: 1.1})
    many = daily(base=16, seed=5, from_offset={-2: 3.0})
    r = compute_retail([RetailInput("cashtag_mentions", "mention_count", counts, breadth_metric="unique_accounts",
                                    breadth=few)], AS_OF, settings)
    assert r.status == "rising"
    assert r.components["sources"]["cashtag_mentions"]["breadth"]["result"] == "too_few_accounts"
    r = compute_retail([RetailInput("cashtag_mentions", "mention_count", counts, breadth_metric="unique_accounts",
                                    breadth=many)], AS_OF, settings)
    assert r.status == "elevated"
    # Outside the post sample: no unique-account data, so rising is the ceiling.
    r = compute_retail([RetailInput("cashtag_mentions", "mention_count", counts, breadth_metric="unique_accounts",
                                    breadth=pd.Series(dtype=float))], AS_OF, settings)
    assert r.status == "rising"
    assert r.components["sources"]["cashtag_mentions"]["breadth"]["result"] == "outside_sample"


def test_retail_unknown_when_no_healthy_source(settings):
    r = compute_retail([RetailInput("cashtag_mentions", "mention_count", daily(days=20, base=30))], AS_OF, settings)
    assert r.status == "unknown"
    assert "insufficient history" in r.components["reason"]
