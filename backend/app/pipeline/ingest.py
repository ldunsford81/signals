"""Ingest: run every enabled adapter, store observations, record per-source health.

Ingest only fetches and stores. Each adapter runs under a timeout and a try/except, so one
failing source never blocks the others, and a failed pull never deletes or overwrites good data.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import and_, delete, insert, select
from sqlalchemy.orm import Session

from app.core import calendar
from app.core.config import Settings
from app.core.logging import get_logger
from app.db.models import Company, Observation, Product, SignalState, Scan, Snapshot, SourceRun, utcnow
from app.sources import registry
from app.sources.base import Entity, FetchResult, SourceAdapter, value_to_date

log = get_logger("ingest")


@dataclass
class RunSummary:
    source: str
    mode: str
    status: str
    rows_written: int
    message: str | None
    last_good_obs_date: date | None


# ---- entities and scope ---------------------------------------------------
def active_tickers(session: Session, settings: Settings, as_of: date) -> set[str]:
    """Names with elevated attention at the latest scan, or inside the earnings window."""
    lo, hi = settings.earnings.window_days
    out: set[str] = set()
    for c in session.scalars(select(Company).where(Company.active.is_(True))):
        if c.next_earnings_date and lo <= (c.next_earnings_date - as_of).days <= hi:
            out.add(c.ticker)
    latest = session.scalar(select(Scan).where(Scan.status == "ok", Scan.trigger != "replay")
                            .order_by(Scan.as_of.desc(), Scan.id.desc()))
    if latest:
        rows = session.execute(
            select(Company.ticker).join(Product, Product.company_id == Company.id)
            .join(SignalState, SignalState.product_id == Product.id)
            .where(SignalState.scan_id == latest.id, SignalState.attention_status == "elevated"))
        out |= {r[0] for r in rows}
    return out


def build_entities(session: Session, settings: Settings, adapter: SourceAdapter, as_of: date) -> list[Entity]:
    cfg = settings.sources[adapter.name]
    companies = list(session.scalars(select(Company).where(Company.active.is_(True)).order_by(Company.id)))
    needs_active = cfg.scope == "active_only" or cfg.sample_scope == "active_only"
    active = active_tickers(session, settings, as_of) if needs_active else set()
    if cfg.scope == "active_only":
        companies = [c for c in companies if c.ticker in active]
    in_sample = (lambda t: t in active) if cfg.sample_scope == "active_only" else (lambda t: True)

    if adapter.entity_type == "product":
        out = []
        for c in companies:
            for p in sorted(c.products, key=lambda p: p.id):
                if p.active:
                    out.append(Entity("product", str(p.id), p.name, c.ticker, tuple(p.keywords or ()),
                                      in_sample(c.ticker)))
        return out
    out = [Entity("company", c.ticker, c.name, c.ticker, (), in_sample(c.ticker),
                  tuple(c.cashtag_exclusions or ())) for c in companies]
    if adapter.name == "price":
        benches = list(dict.fromkeys([*cfg.benchmarks, *(c.benchmark_ticker for c in companies)]))
        out += [Entity("benchmark", b, b) for b in benches if b]
    return out


# ---- windows ----------------------------------------------------------------
def last_good_date(session: Session, source: str) -> date | None:
    return session.scalar(select(SourceRun.last_good_obs_date)
                          .where(SourceRun.source == source, SourceRun.last_good_obs_date.is_not(None))
                          .order_by(SourceRun.id.desc()).limit(1))


def fetch_window(session: Session, settings: Settings, adapter: SourceAdapter, end: date,
                 full_history: bool) -> tuple[date, date]:
    history = settings.demo.history_days
    if adapter.rescales_history:
        days = settings.sources[adapter.name].snapshot_window_days or history
        return end - timedelta(days=days), end
    if full_history:
        return end - timedelta(days=history), end
    last = last_good_date(session, adapter.name)
    if last:
        start = last - timedelta(days=settings.ingest.overlap_days)
    else:
        start = end - timedelta(days=settings.ingest.default_lookback_days)
    return max(start, end - timedelta(days=history)), end


# ---- storage ------------------------------------------------------------------
def store(session: Session, adapter: SourceAdapter, result: FetchResult) -> tuple[int, date | None]:
    obs = result.observations
    if not obs:
        return 0, None
    now = utcnow()
    rows_written = 0
    if adapter.rescales_history and result.snapshot:
        snap = result.snapshot
        by_entity: dict[str, list] = {}
        for o in obs:
            by_entity.setdefault(o.entity_key, []).append(o)
        for key, items in by_entity.items():
            # A re-pull of the identical window replaces that snapshot; older snapshots are kept.
            old = session.scalars(select(Snapshot.id).where(
                Snapshot.source == adapter.name, Snapshot.entity_key == key,
                Snapshot.window_start == snap.window_start, Snapshot.window_end == snap.window_end)).all()
            if old:
                session.execute(delete(Observation).where(Observation.snapshot_id.in_(old)))
                session.execute(delete(Snapshot).where(Snapshot.id.in_(old)))
            s = Snapshot(source=adapter.name, entity_key=key, pulled_at=now,
                         window_start=snap.window_start, window_end=snap.window_end)
            session.add(s)
            session.flush()
            session.execute(insert(Observation), [
                dict(source=adapter.name, entity_type=o.entity_type, entity_key=o.entity_key, metric=o.metric,
                     obs_date=o.obs_date, value=o.value, snapshot_id=s.id, ingested_at=now) for o in items])
            rows_written += len(items)
    else:
        groups: dict[tuple[str, str, str], list] = {}
        for o in obs:
            groups.setdefault((o.entity_type, o.entity_key, o.metric), []).append(o)
        for (etype, key, metric), items in groups.items():
            dates = [o.obs_date for o in items]
            for i in range(0, len(dates), 500):
                session.execute(delete(Observation).where(and_(
                    Observation.source == adapter.name, Observation.entity_type == etype,
                    Observation.entity_key == key, Observation.metric == metric,
                    Observation.snapshot_id.is_(None), Observation.obs_date.in_(dates[i:i + 500]))))
        session.execute(insert(Observation), [
            dict(source=adapter.name, entity_type=o.entity_type, entity_key=o.entity_key, metric=o.metric,
                 obs_date=o.obs_date, value=o.value, snapshot_id=None, ingested_at=now) for o in obs])
        rows_written = len(obs)
    return rows_written, max(o.obs_date for o in obs)


def apply_catalog(session: Session, result: FetchResult) -> None:
    """Earnings is a catalog source: copy each company's latest reported values onto the catalog row."""
    latest: dict[str, dict] = {}
    for o in result.observations:
        cur = latest.setdefault(o.entity_key, {})
        if o.metric not in cur or o.obs_date >= cur[o.metric][0]:
            cur[o.metric] = (o.obs_date, o.value)
    for ticker, vals in latest.items():
        c = session.scalar(select(Company).where(Company.ticker == ticker))
        if not c:
            continue
        if "next_earnings_date" in vals:
            c.next_earnings_date = value_to_date(vals["next_earnings_date"][1])
        if "confirmed" in vals:
            c.earnings_date_confirmed = bool(vals["confirmed"][1])
        if "fiscal_quarter_end" in vals:
            c.fiscal_quarter_end = value_to_date(vals["fiscal_quarter_end"][1])


# ---- runner ---------------------------------------------------------------------
def _record(session: Session, name: str, mode: str, started, status: str, rows: int, msg: str | None,
            last_good: date | None) -> RunSummary:
    session.add(SourceRun(source=name, mode=mode, started_at=started, finished_at=utcnow(), status=status,
                          rows_written=rows, error_message=msg, last_good_obs_date=last_good))
    session.commit()
    log.info("source=%s mode=%s status=%s rows=%d last_good=%s%s", name, mode, status, rows, last_good,
             f" message={msg!r}" if msg else "")
    return RunSummary(name, mode, status, rows, msg, last_good)


def run_source(session: Session, settings: Settings, name: str, as_of: date, full_history: bool = False) -> RunSummary:
    cfg = settings.sources[name]
    started = utcnow()
    prev_good = last_good_date(session, name)
    if cfg.mode == "off":
        return _record(session, name, cfg.mode, started, "skipped", 0, "source is off in config", prev_good)
    try:
        adapter = registry.build(name, settings)
    except Exception as e:  # noqa: BLE001 - one bad source must not block the rest
        return _record(session, name, cfg.mode, started, "error", 0, f"could not build adapter: {e}", prev_good)
    if adapter is None:
        return _record(session, name, cfg.mode, started, "skipped", 0,
                       f"no '{cfg.mode}' implementation for {name} yet", prev_good)
    missing = [k for k in adapter.required_settings() if not os.environ.get(k)]
    if missing:
        return _record(session, name, cfg.mode, started, "skipped", 0,
                       f"missing settings {', '.join(missing)} (add them to .env)", prev_good)
    entities = build_entities(session, settings, adapter, as_of)
    if not entities:
        return _record(session, name, cfg.mode, started, "skipped", 0, "no entities in scope", prev_good)
    start, end = fetch_window(session, settings, adapter, as_of, full_history)

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        result = pool.submit(adapter.fetch, entities, start, end).result(timeout=settings.ingest.timeout_seconds)
    except FutureTimeout:
        return _record(session, name, cfg.mode, started, "error", 0,
                       f"timed out after {settings.ingest.timeout_seconds}s", prev_good)
    except Exception as e:  # noqa: BLE001
        return _record(session, name, cfg.mode, started, "error", 0, f"{type(e).__name__}: {e}", prev_good)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    try:
        rows, last = store(session, adapter, result)
        if adapter.family == "catalog":
            apply_catalog(session, result)
        session.commit()
    except Exception as e:  # noqa: BLE001
        session.rollback()
        return _record(session, name, cfg.mode, started, "error", 0, f"storing failed: {e}", prev_good)

    status = "partial" if result.warnings else "ok"
    msg = "; ".join(result.warnings[:10]) or None
    return _record(session, name, cfg.mode, started, status, rows, msg, max(filter(None, [last, prev_good]), default=None))


def run_ingest(session: Session, settings: Settings, as_of: date | None = None, only: list[str] | None = None,
               full_history: bool = False) -> list[RunSummary]:
    as_of = as_of or calendar.last_completed_session()
    names = [n for n in registry.source_names(settings) if not only or n in only]
    unknown = set(only or []) - set(settings.sources)
    if unknown:
        raise ValueError(f"unknown source(s): {', '.join(sorted(unknown))}")
    return [run_source(session, settings, n, as_of, full_history) for n in names]
