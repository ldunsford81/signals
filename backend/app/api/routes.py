"""FastAPI routers. No business logic here: read stored results, or call the pipeline jobs."""
from __future__ import annotations

from datetime import date
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    AttentionBadge,
    JobOut,
    PriceBadge,
    ProductDetailOut,
    RetailBadge,
    RunRequest,
    ScanInfo,
    SourceStatus,
    StatusOut,
    WatchlistOut,
    WatchlistRow,
)
from app.core import calendar
from app.core.config import ConfigError, Settings, load_settings
from app.db.models import Company, Product, Scan, SignalState, SourceRun
from app.db.session import session_factory
from app.pipeline import jobs
from app.pipeline.detail import NotFound, product_detail
from app.sources.demo.state import stored_anchor

router = APIRouter(prefix="/api")


def get_session() -> Iterator[Session]:
    s = session_factory()()
    try:
        yield s
    finally:
        s.close()


def latest_scan(session: Session, include_replay: bool = False) -> Scan | None:
    q = select(Scan).where(Scan.status == "ok")
    if not include_replay:
        q = q.where(Scan.trigger != "replay")
    return session.scalar(q.order_by(Scan.as_of.desc(), Scan.id.desc()).limit(1))


def scan_info(s: Scan | None) -> ScanInfo | None:
    return ScanInfo.model_validate(s, from_attributes=True) if s else None


def source_statuses(session: Session, settings: Settings, ref_date: date) -> list[SourceStatus]:
    out = []
    for name, cfg in settings.sources.items():
        run = session.scalar(select(SourceRun).where(SourceRun.source == name).order_by(SourceRun.id.desc()).limit(1))
        good = session.scalar(select(SourceRun.last_good_obs_date).where(
            SourceRun.source == name, SourceRun.last_good_obs_date.is_not(None)).order_by(SourceRun.id.desc()).limit(1))
        limit = settings.health.max_staleness_days.get(name)
        stale = bool(limit is not None and cfg.mode != "off" and (good is None or (ref_date - good).days > limit))
        out.append(SourceStatus(source=name, mode=cfg.mode, scope=cfg.scope, last_run_status=run.status if run else None,
                                last_run_at=run.finished_at if run else None, rows_written=run.rows_written if run else None,
                                last_good_obs_date=good, error_message=run.error_message if run else None,
                                stale=stale, staleness_limit_days=limit))
    return out


@router.get("/status", response_model=StatusOut)
def status(session: Session = Depends(get_session)) -> StatusOut:
    settings = load_settings()
    scan = latest_scan(session)
    ref = scan.as_of if scan else calendar.last_completed_session()
    sources = source_statuses(session, settings, ref)
    warnings = []
    for s in sources:
        if s.last_run_status == "error":
            warnings.append(f"{s.source}: last ingest failed — {s.error_message}")
        elif s.last_run_status == "partial":
            warnings.append(f"{s.source}: last ingest was partial — {s.error_message}")
        elif s.last_run_status == "skipped" and s.mode != "off":
            warnings.append(f"{s.source}: skipped — {s.error_message}")
        if s.stale:
            warnings.append(f"{s.source}: stale (last good data {s.last_good_obs_date}, limit {s.staleness_limit_days}d)")
    if scan is None:
        warnings.append("No scan has run yet. Run `ctm scan` or press Run daily.")
    demo = any(c.mode == "demo" for c in settings.sources.values())
    return StatusOut(as_of=scan.as_of if scan else None, latest_scan=scan_info(scan), config_hash=settings.hash(),
                     demo_mode=demo, demo_anchor_date=stored_anchor() if demo else None, warnings=warnings,
                     sources=sources)


def _row(st: SignalState, p: Product, c: Company) -> WatchlistRow:
    h = st.input_health or {}
    flags = h.get("flags", {})
    earn = h.get("earnings", {})
    ac, pc, rc = st.attention_components or {}, st.price_components or {}, st.retail_components or {}
    return WatchlistRow(
        product_id=p.id, product=p.name, company_id=c.id, company=c.name, ticker=c.ticker, is_demo=c.is_demo,
        stage=st.stage,
        attention=AttentionBadge(status=st.attention_status, reason=ac.get("reason"), score=st.attention_score,
                                 single_source=bool(flags.get("single_source")) and st.attention_status == "elevated",
                                 seasonal=st.attention_status == "seasonal"),
        price=PriceBadge(status=st.price_response, reason=pc.get("reason"), relative_return=pc.get("relative_return"),
                         volume_ratio=pc.get("volume_ratio"), benchmark=pc.get("benchmark")),
        retail=RetailBadge(status=st.retail_status, reason=rc.get("reason"), set_by=rc.get("set_by")),
        signal_start_date=st.signal_start_date, days_to_earnings=st.days_to_earnings,
        next_earnings_date=earn.get("next_earnings_date"), earnings_projected=earn.get("confirmed") is False,
        earnings_status=earn.get("status", "unknown"), earnings_reason=earn.get("reason"),
        days_left_in_quarter=st.days_left_in_quarter, quarter_closed=bool(flags.get("quarter_closed")),
        rescaled_history=bool(flags.get("rescaled_history")),
    )


@router.get("/watchlist", response_model=WatchlistOut)
def watchlist(
    session: Session = Depends(get_session),
    scan_id: int | None = None,
    stage: list[str] | None = Query(None),
    attention: list[str] | None = Query(None),
    price: list[str] | None = Query(None),
    retail: list[str] | None = Query(None),
    earnings_window: bool = True,
) -> WatchlistOut:
    settings = load_settings()
    scan = session.get(Scan, scan_id) if scan_id else latest_scan(session)
    lo, hi = settings.earnings.window_days
    order = settings.stage_priority
    if scan is None:
        return WatchlistOut(scan=None, earnings_window_days=(lo, hi), stage_order=order, total=0, rows=[])
    q = (select(SignalState, Product, Company).join(Product, Product.id == SignalState.product_id)
         .join(Company, Company.id == Product.company_id).where(SignalState.scan_id == scan.id))
    rows = [_row(*r) for r in session.execute(q).all()]
    total = len(rows)
    if stage:
        rows = [r for r in rows if r.stage in stage]
    if attention:
        rows = [r for r in rows if r.attention.status in attention]
    if price:
        rows = [r for r in rows if r.price.status in price]
    if retail:
        rows = [r for r in rows if r.retail.status in retail]
    if earnings_window:
        rows = [r for r in rows if r.days_to_earnings is not None and r.earnings_status != "unknown"
                and lo <= r.days_to_earnings <= hi]
    rank = {s: i for i, s in enumerate(order)}
    rows.sort(key=lambda r: (rank.get(r.stage, len(order)), -(r.attention.score or float("-inf")), r.ticker, r.product))
    return WatchlistOut(scan=scan_info(scan), earnings_window_days=(lo, hi), stage_order=order, total=total, rows=rows)


@router.get("/products/{product_id}", response_model=ProductDetailOut)
def product(product_id: int, scan_id: int | None = None, days: int = Query(180, ge=30, le=400),
            session: Session = Depends(get_session)) -> ProductDetailOut:
    try:
        return ProductDetailOut.model_validate(product_detail(session, load_settings(), product_id, scan_id, days))
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


def _job(fn, *a, **kw) -> JobOut:
    try:
        return JobOut(ok=True, result=jobs.to_json(fn(*a, **kw)))
    except ConfigError as e:
        return JobOut(ok=False, error=str(e))
    except Exception as e:  # noqa: BLE001 - surface to the UI rather than a 500
        return JobOut(ok=False, error=f"{type(e).__name__}: {e}")


@router.post("/ingest", response_model=JobOut)
def ingest(req: RunRequest | None = None) -> JobOut:
    req = req or RunRequest()
    return _job(jobs.ingest_job, as_of=req.as_of, sources=req.sources)


@router.post("/scan", response_model=JobOut)
def scan(req: RunRequest | None = None) -> JobOut:
    req = req or RunRequest()
    return _job(jobs.scan_job, as_of=req.as_of, trigger="manual")


@router.post("/daily", response_model=JobOut)
def daily(req: RunRequest | None = None) -> JobOut:
    req = req or RunRequest()
    return _job(jobs.daily_job, as_of=req.as_of, trigger="manual")
