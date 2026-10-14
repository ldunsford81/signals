"""Read model for the per-product Detail screen.

Everything the charts need is computed here (bands, rebasing, markers) so the frontend only draws.
Series are read point-in-time at the scan's as_of with the same store the scan used.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Alert, Announcement, Company, Product, Scan, SignalState
from app.signals.health import num, window_stats
from app.signals.store import ObservationRepository


class NotFound(Exception):
    pass


def _iso(ts) -> str:
    return pd.Timestamp(ts).date().isoformat()


def band_series(series: pd.Series, as_of: date, short: int, baseline: tuple[int, int], start: date,
                breadth: pd.Series | None = None) -> list[dict]:
    """Daily value, short-window mean and the baseline band (mean ± 2 std) from `start` to as_of."""
    st = window_stats(series, as_of, short, baseline)
    if st.empty:
        return []
    st = st.loc[pd.Timestamp(start):]
    if breadth is not None and not breadth.empty:
        bst = window_stats(breadth, as_of, short, baseline).reindex(st.index)
    else:
        bst = None
    out = []
    for ts, row in st.iterrows():
        mean, std = row["base_mean"], row["base_std"]
        point = {"date": _iso(ts), "value": num(row["value"]), "short_mean": num(row["short_mean"]),
                 "baseline_mean": num(mean),
                 "band_low": num(mean - 2 * std) if pd.notna(std) else None,
                 "band_high": num(mean + 2 * std) if pd.notna(std) else None,
                 "ratio": num(row["ratio"]), "z": num(row["z"])}
        if bst is not None:
            point["breadth_value"] = num(bst.loc[ts, "value"])
            point["breadth_short_mean"] = num(bst.loc[ts, "short_mean"])
        out.append(point)
    return out


def price_series(close: pd.Series, volume: pd.Series, bench: pd.Series, base_date: date | None,
                 start: date) -> tuple[list[dict], float | None]:
    """Close and volume, plus the benchmark rebased to the stock's close on the anchor base date."""
    if close.empty:
        return [], None
    scale = None
    if base_date is not None and not bench.empty:
        b0 = bench.loc[:pd.Timestamp(base_date)]
        c0 = close.loc[:pd.Timestamp(base_date)]
        if not b0.empty and not c0.empty and b0.iloc[-1] > 0:
            scale = float(c0.iloc[-1]) / float(b0.iloc[-1])
    win = close.loc[pd.Timestamp(start):]
    out = []
    for ts, c in win.items():
        b = bench.get(ts, np.nan) if not bench.empty else np.nan
        out.append({"date": _iso(ts), "close": num(c), "volume": num(volume.get(ts, np.nan)),
                    "benchmark_rebased": num(b * scale) if scale is not None and pd.notna(b) else None})
    return out, num(scale)


def product_detail(session: Session, settings: Settings, product_id: int, scan_id: int | None = None,
                   days: int = 180) -> dict:
    product = session.get(Product, product_id)
    if product is None:
        raise NotFound(f"product {product_id} not found")
    company = session.get(Company, product.company_id)

    q = (select(SignalState, Scan).join(Scan, Scan.id == SignalState.scan_id)
         .where(SignalState.product_id == product_id, Scan.status == "ok"))
    if scan_id is not None:
        q = q.where(Scan.id == scan_id)
    else:
        q = q.where(Scan.trigger != "replay")
    row = session.execute(q.order_by(Scan.as_of.desc(), Scan.id.desc()).limit(1)).first()
    state, scan = (row if row else (None, None))
    as_of = scan.as_of if scan else None

    out: dict = {
        "product": {"id": product.id, "name": product.name, "keywords": product.keywords or [],
                    "launched_on": product.launched_on.isoformat() if product.launched_on else None,
                    "active": product.active},
        "company": {"id": company.id, "ticker": company.ticker, "name": company.name, "sector": company.sector,
                    "benchmark": company.benchmark_ticker, "market_cap_usd_m": company.market_cap_usd_m,
                    "analyst_count": company.analyst_count, "is_demo": company.is_demo},
        "scan": None, "state": None, "window_start": None, "attention_series": [], "price_series": [],
        "retail_series": [], "announcements": [], "history": [], "alerts": [],
    }
    out["history"] = stage_history(session, product_id)
    out["alerts"] = product_alerts(session, product_id)
    if state is None:
        return out

    start = as_of - timedelta(days=days - 1)
    out["scan"] = {"id": scan.id, "as_of": as_of.isoformat(), "trigger": scan.trigger,
                   "config_hash": scan.config_hash,
                   "finished_at": scan.finished_at.isoformat() if scan.finished_at else None}
    out["window_start"] = start.isoformat()
    out["state"] = {
        "stage": state.stage, "attention_status": state.attention_status, "attention_score": state.attention_score,
        "attention_components": state.attention_components, "price_response": state.price_response,
        "price_components": state.price_components, "retail_status": state.retail_status,
        "retail_components": state.retail_components,
        "signal_start_date": state.signal_start_date.isoformat() if state.signal_start_date else None,
        "days_to_earnings": state.days_to_earnings, "days_left_in_quarter": state.days_left_in_quarter,
        "input_health": state.input_health,
    }

    # Series, read point in time exactly as the scan did.
    lookback = max(days, 365) + settings.attention.baseline_window[1] + 30
    repo = ObservationRepository(session, since=as_of - timedelta(days=lookback))
    view = repo.at(as_of)
    att_cfg, ret_cfg = settings.attention, settings.retail
    for ref in settings.families.attention:
        s, info = view.series(ref.source, str(product.id), ref.metric)
        out["attention_series"].append({
            "source": ref.source, "metric": ref.metric, "short_window": att_cfg.short_window,
            "rescaled_history": info.rescaled_history,
            "points": band_series(s, as_of, att_cfg.short_window, tuple(att_cfg.baseline_window), start)})
    for ref in settings.families.retail:
        s, info = view.series(ref.source, company.ticker, ref.metric)
        breadth = view.series(ref.source, company.ticker, ref.breadth_metric)[0] if ref.breadth_metric else None
        out["retail_series"].append({
            "source": ref.source, "metric": ref.metric, "breadth_metric": ref.breadth_metric,
            "short_window": ret_cfg.short_window, "rescaled_history": info.rescaled_history,
            "points": band_series(s, as_of, ret_cfg.short_window, tuple(ret_cfg.baseline_window), start, breadth)})
    fam = settings.families.price
    close, _ = view.series(fam.close.source, company.ticker, fam.close.metric)
    volume, _ = view.series(fam.volume.source, company.ticker, fam.volume.metric)
    bench, _ = view.series(fam.close.source, company.benchmark_ticker, fam.close.metric)
    base = state.price_components.get("base_date")
    if base:
        rebase_on = date.fromisoformat(base)
    else:  # no anchor (e.g. price unknown): rebase at the first close in the window
        in_window = close.loc[pd.Timestamp(start):]
        rebase_on = in_window.index[0].date() if not in_window.empty else None
    points, scale = price_series(close, volume, bench, rebase_on, start)
    out["price_series"] = points
    out["benchmark_scale"] = scale
    out["benchmark_rebased_on"] = rebase_on.isoformat() if rebase_on else None

    anns = session.scalars(select(Announcement).where(
        Announcement.company_id == company.id, Announcement.event_date >= start, Announcement.event_date <= as_of)
        .order_by(Announcement.event_date)).all()
    out["announcements"] = [{"id": a.id, "event_date": a.event_date.isoformat(), "type": a.type, "title": a.title,
                             "url": a.url, "product_id": a.product_id} for a in anns
                            if a.product_id in (None, product.id)]
    return out


def stage_history(session: Session, product_id: int) -> list[dict]:
    """This product's stage at every non-replay scan, newest first."""
    rows = session.execute(
        select(SignalState, Scan).join(Scan, Scan.id == SignalState.scan_id)
        .where(SignalState.product_id == product_id, Scan.status == "ok", Scan.trigger != "replay")
        .order_by(Scan.as_of.desc(), Scan.id.desc())).all()
    return [{"scan_id": sc.id, "as_of": sc.as_of.isoformat(), "trigger": sc.trigger, "config_hash": sc.config_hash,
             "stage": st.stage, "attention": st.attention_status, "price": st.price_response,
             "retail": st.retail_status, "days_to_earnings": st.days_to_earnings} for st, sc in rows]


def product_alerts(session: Session, product_id: int) -> list[dict]:
    rows = session.execute(select(Alert, Scan).join(Scan, Scan.id == Alert.scan_id)
                           .where(Alert.product_id == product_id)
                           .order_by(Alert.as_of.desc(), Alert.id.desc())).all()
    return [{"id": a.id, "as_of": a.as_of.isoformat(), "stage": a.stage, "prior_stage": a.prior_stage,
             "changed_fields": a.changed_fields, "summary": a.summary, "config_hash": a.config_hash,
             "trigger": sc.trigger, "created_at": a.created_at.isoformat()} for a, sc in rows]
