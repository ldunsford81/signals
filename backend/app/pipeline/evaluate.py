"""Evaluate: forward returns for every alert, and the rules-performance summary.

Horizons are trading days after the alert date (close to close), plus `through_earnings`
(alert date to the close of the first session after the earnings date). An outcome is
`complete` once its end date has a stored close; until then it holds the return so far.
"""
from __future__ import annotations

import re
import statistics
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import calendar
from app.core.config import Settings
from app.core.logging import get_logger
from app.db.models import Alert, AlertOutcome, Company, Product, Scan, utcnow
from app.pipeline.feed import latest_review
from app.signals.store import ObservationRepository

log = get_logger("evaluate")


def horizon_names(settings: Settings) -> list[str]:
    names = [f"{n}d" for n in settings.evaluation.horizons_trading_days]
    return names + (["through_earnings"] if settings.evaluation.include_through_earnings else [])


def hit_rule(settings: Settings, stage: str) -> tuple[int, str | None, str]:
    """(direction, headline horizon or None, rule text). direction +1 = hit on positive excess."""
    rule = settings.evaluation.hit.get(stage, "positive_excess")
    m = re.fullmatch(r"(positive|negative)_excess(?:_(\d+d))?", rule)
    return (1 if m.group(1) == "positive" else -1), m.group(2), rule


def trigger_group(trigger: str) -> str:
    return "replay" if trigger == "replay" else "live"


# ---- forward returns --------------------------------------------------------------
def _end_dates(alert: Alert, settings: Settings) -> dict[str, date]:
    out = {}
    for n in settings.evaluation.horizons_trading_days:
        try:
            out[f"{n}d"] = calendar.add_sessions(alert.as_of, n)
        except Exception:  # beyond the offline calendar
            continue
    if settings.evaluation.include_through_earnings:
        ed = (alert.input_snapshot.get("earnings") or {}).get("next_earnings_date")
        if ed and date.fromisoformat(ed) >= alert.as_of:
            try:
                out["through_earnings"] = calendar.session_on_or_after(date.fromisoformat(ed) + timedelta(days=1))
            except Exception:
                pass
    return out


def _ret(series: pd.Series, start: date, end: date) -> float | None:
    a, b = series.loc[:pd.Timestamp(start)], series.loc[:pd.Timestamp(end)]
    if a.empty or b.empty or b.index[-1] <= a.index[-1]:
        return None
    return float(b.iloc[-1] / a.iloc[-1] - 1)


def run_evaluate(session: Session, settings: Settings) -> dict:
    alerts = session.scalars(select(Alert).order_by(Alert.id)).all()
    existing = {(o.alert_id, o.horizon): o for o in session.scalars(select(AlertOutcome))}
    repo = ObservationRepository(session, sources=["price"])
    written = completed = skipped = 0
    for a in alerts:
        comp = a.input_snapshot.get("company") or {}
        ticker = comp.get("ticker") or session.get(Company, a.company_id).ticker
        bench_ticker = comp.get("benchmark") or session.get(Company, a.company_id).benchmark_ticker
        close = repo.raw("price", ticker, "close")
        bench = repo.raw("price", bench_ticker, "close")
        if close.empty or bench.empty:
            skipped += 1
            continue
        last = min(close.index[-1], bench.index[-1]).date()
        for horizon, end in _end_dates(a, settings).items():
            row = existing.get((a.id, horizon))
            if row is not None and row.complete:
                continue
            complete = end <= last
            upto = end if complete else min(end, last)
            s, b = _ret(close, a.as_of, upto), _ret(bench, a.as_of, upto)
            if row is None:
                row = AlertOutcome(alert_id=a.id, horizon=horizon)
                session.add(row)
            row.stock_return, row.benchmark_return = s, b
            row.excess_return = (s - b) if s is not None and b is not None else None
            row.complete, row.computed_at = complete, utcnow()
            written += 1
            completed += int(complete)
    session.commit()
    log.info("evaluate: %d alerts, %d outcomes written (%d complete), %d alerts skipped (no prices)",
             len(alerts), written, completed, skipped)
    return {"alerts": len(alerts), "outcomes_written": written, "outcomes_completed": completed,
            "alerts_skipped": skipped}


# ---- dedupe and performance -------------------------------------------------------
def counted_ids(rows: list[tuple[Alert, Scan]], dedupe_days: int, combine: bool = False) -> set[int]:
    """First alert per company per stage within `dedupe_days` counts once (per config + trigger group)."""
    counted: set[int] = set()
    last_counted: dict[tuple, date] = {}
    for a, sc in sorted(rows, key=lambda r: (r[0].as_of, r[0].id)):
        key = (a.company_id, a.stage, a.config_hash, "all" if combine else trigger_group(sc.trigger))
        prev = last_counted.get(key)
        if prev is None or (a.as_of - prev).days > dedupe_days:
            counted.add(a.id)
            last_counted[key] = a.as_of
    return counted


def performance(session: Session, settings: Settings, combine_triggers: bool = False) -> dict:
    ev = settings.evaluation
    horizons = horizon_names(settings)
    rows = session.execute(select(Alert, Scan).join(Scan, Scan.id == Alert.scan_id)).all()
    counted = counted_ids(rows, ev.dedupe_days, combine_triggers)
    outcomes: dict[int, dict[str, AlertOutcome]] = {}
    for o in session.scalars(select(AlertOutcome)):
        outcomes.setdefault(o.alert_id, {})[o.horizon] = o

    groups: dict[tuple, dict] = {}
    for a, sc in rows:
        tg = "all" if combine_triggers else trigger_group(sc.trigger)
        key = (a.stage, a.config_hash, tg)
        direction, headline, rule = hit_rule(settings, a.stage)
        g = groups.setdefault(key, {"stage": a.stage, "config_hash": a.config_hash, "trigger": tg, "n_alerts": 0,
                                    "n_counted": 0, "hit_rule": rule, "headline_horizon": headline,
                                    "first_as_of": a.as_of, "last_as_of": a.as_of, "_x": {h: [] for h in horizons}})
        g["n_alerts"] += 1
        g["first_as_of"], g["last_as_of"] = min(g["first_as_of"], a.as_of), max(g["last_as_of"], a.as_of)
        if a.id not in counted:
            continue
        g["n_counted"] += 1
        for h in horizons:
            o = outcomes.get(a.id, {}).get(h)
            if o is not None and o.complete and o.excess_return is not None:
                g["_x"][h].append(o.excess_return)

    out = []
    for g in groups.values():
        direction = hit_rule(settings, g["stage"])[0]
        stats = {}
        for h in horizons:
            xs = g["_x"][h]
            hits = sum(1 for x in xs if x * direction > 0)
            stats[h] = {"n": len(xs), "hits": hits, "hit_rate": hits / len(xs) if xs else None,
                        "median_excess": statistics.median(xs) if xs else None,
                        "mean_excess": statistics.fmean(xs) if xs else None,
                        "judged": len(xs) >= ev.min_sample_to_judge}
        del g["_x"]
        g["horizons"] = stats
        out.append(g)
    order = {s: i for i, s in enumerate(settings.stage_priority)}
    out.sort(key=lambda g: (g["trigger"] != "live", order.get(g["stage"], 99), str(g["last_as_of"])))
    return {"horizons": horizons, "min_sample_to_judge": ev.min_sample_to_judge, "dedupe_days": ev.dedupe_days,
            "combine_triggers": combine_triggers, "current_config_hash": settings.hash(), "groups": out}


# ---- alert log ------------------------------------------------------------------------
def list_alerts(session: Session, settings: Settings, stage: str | None = None, trigger: str | None = None,
                config_hash: str | None = None, start: date | None = None, end: date | None = None,
                limit: int = 200, offset: int = 0) -> dict:
    q = (select(Alert, Scan, Product, Company).join(Scan, Scan.id == Alert.scan_id)
         .join(Product, Product.id == Alert.product_id).join(Company, Company.id == Alert.company_id))
    if stage:
        q = q.where(Alert.stage == stage)
    if trigger == "replay":
        q = q.where(Scan.trigger == "replay")
    elif trigger == "live":
        q = q.where(Scan.trigger != "replay")
    if config_hash:
        q = q.where(Alert.config_hash == config_hash)
    if start:
        q = q.where(Alert.as_of >= start)
    if end:
        q = q.where(Alert.as_of <= end)
    rows = session.execute(q.order_by(Alert.as_of.desc(), Alert.id.desc())).all()
    all_rows = session.execute(select(Alert, Scan).join(Scan, Scan.id == Alert.scan_id)).all()
    counted = counted_ids(all_rows, settings.evaluation.dedupe_days)
    page = rows[offset:offset + limit]
    ids = [a.id for a, *_ in page]
    outcomes: dict[int, dict] = {}
    if ids:
        for o in session.scalars(select(AlertOutcome).where(AlertOutcome.alert_id.in_(ids))):
            outcomes.setdefault(o.alert_id, {})[o.horizon] = {
                "stock_return": o.stock_return, "benchmark_return": o.benchmark_return,
                "excess_return": o.excess_return, "complete": o.complete}
    items = []
    for a, sc, p, c in page:
        review = latest_review(session, a.id)
        items.append({"id": a.id, "as_of": a.as_of, "stage": a.stage, "prior_stage": a.prior_stage,
                      "product_id": p.id, "product": p.name, "company": c.name, "ticker": c.ticker,
                      "trigger": sc.trigger, "config_hash": a.config_hash, "summary": a.summary,
                      "changed_fields": a.changed_fields, "counted": a.id in counted,
                      "rescaled_history": bool((a.input_snapshot.get("input_health") or {}).get("flags", {})
                                               .get("rescaled_history")),
                      "decision": review.decision if review else "unreviewed",
                      "outcomes": outcomes.get(a.id, {})})
    configs = sorted({a.config_hash for a, _ in all_rows})
    return {"total": len(rows), "items": items, "horizons": horizon_names(settings), "config_hashes": configs}


def alert_detail(session: Session, alert_id: int) -> dict | None:
    a = session.get(Alert, alert_id)
    if a is None:
        return None
    sc = session.get(Scan, a.scan_id)
    outs = {o.horizon: {"stock_return": o.stock_return, "benchmark_return": o.benchmark_return,
                        "excess_return": o.excess_return, "complete": o.complete,
                        "computed_at": o.computed_at}
            for o in session.scalars(select(AlertOutcome).where(AlertOutcome.alert_id == a.id))}
    return {"id": a.id, "as_of": a.as_of, "stage": a.stage, "prior_stage": a.prior_stage, "trigger": sc.trigger,
            "scan_id": a.scan_id, "product_id": a.product_id, "company_id": a.company_id, "summary": a.summary,
            "changed_fields": a.changed_fields, "config_hash": a.config_hash, "created_at": a.created_at,
            "input_snapshot": a.input_snapshot, "outcomes": outs}
