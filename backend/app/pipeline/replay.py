"""Replay: run the normal scan for every trading day in a range, tagged trigger=replay.

Observations are loaded once and every scan reads them point in time through the same store the
daily scan uses, so a replayed day sees only data dated on or before it. Search snapshots pulled
later than the replayed day are truncated and flagged `rescaled_history`.
"""
from __future__ import annotations

import time
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import calendar
from app.core.config import Settings
from app.core.logging import get_logger
from app.db.models import Observation, Scan
from app.pipeline.scan import ensure_config_version, run_scan
from app.signals.store import ObservationRepository

log = get_logger("replay")


def default_range(session: Session, settings: Settings) -> tuple[date, date]:
    """From the first day with enough attention history to the last day with price data."""
    first = session.scalar(select(func.min(Observation.obs_date)))
    last = session.scalar(select(func.max(Observation.obs_date)).where(Observation.source == "price"))
    if first is None or last is None:
        raise ValueError("no observations stored yet; run `socialarb seed` or `socialarb ingest` first")
    start = first + timedelta(days=settings.health.min_history_days["attention"])
    end = min(last, calendar.last_completed_session())
    return calendar.session_on_or_after(start), calendar.session_on_or_before(end)


def run_replay(session: Session, settings: Settings, start: date | None = None, end: date | None = None) -> dict:
    d_start, d_end = default_range(session, settings)
    start, end = start or d_start, end or d_end
    if start > end:
        raise ValueError(f"replay start {start} is after end {end}")
    chash = ensure_config_version(session, settings)
    session.commit()
    done = set(session.scalars(select(Scan.as_of).where(Scan.trigger == "replay", Scan.status == "ok",
                                                        Scan.config_hash == chash)))
    days = [d for d in calendar.sessions_between(start, end) if d not in done]
    t0 = time.time()
    repo = ObservationRepository(session)
    alerts, stages = 0, {}
    for i, d in enumerate(days, 1):
        r = run_scan(session, settings, as_of=d, trigger="replay", repo=repo)
        alerts += r.alerts_created
        for k, v in r.stages.items():
            stages[k] = stages.get(k, 0) + v
        if i % 25 == 0:
            log.info("replay %d/%d (as_of %s, %d alerts so far)", i, len(days), d, alerts)
    log.info("replay %s..%s config=%s: %d scans (%d already done), %d alerts in %.0fs", start, end, chash,
             len(days), len(done), alerts, time.time() - t0)
    return {"start": start, "end": end, "config_hash": chash, "scans_run": len(days),
            "scans_skipped": len(done & set(calendar.sessions_between(start, end))),
            "alerts_created": alerts, "product_days_by_stage": stages}
