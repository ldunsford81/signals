"""Scan: read stored observations as of a date, compute statuses and stages, write alerts.

Scan never calls adapters. `scan(as_of)` reads only observations dated on or before `as_of`,
so the same code powers the daily scan and historical replay.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core import calendar
from app.core.config import Settings
from app.core.logging import get_logger
from app.db.models import Alert, Announcement, Company, ConfigVersion, Product, Scan, SignalState, utcnow
from app.signals.attention import AttentionResult, SourceInput, compute_attention
from app.signals.earnings import EarningsResult, compute_earnings
from app.signals.price import PriceResult, compute_price
from app.signals.retail import RetailInput, RetailResult, compute_retail
from app.signals.store import AsOfView, ObservationRepository
from app.stages.engine import StageInputs, evaluate

log = get_logger("scan")

TRACKED_FIELDS = [("stage", "Stage"), ("price_response", "Price"), ("retail_status", "Retail")]


@dataclass
class ScanResult:
    scan_id: int
    as_of: date
    trigger: str
    config_hash: str
    products: int
    stages: dict[str, int] = field(default_factory=dict)
    alerts_created: int = 0


def resolve_as_of(as_of: date | None) -> date:
    """Default: the last completed US trading session. Non-trading dates roll back to the prior session."""
    return calendar.last_completed_session() if as_of is None else calendar.session_on_or_before(as_of)


def ensure_config_version(session: Session, settings: Settings) -> str:
    h = settings.hash()
    if not session.scalar(select(ConfigVersion).where(ConfigVersion.config_hash == h)):
        session.add(ConfigVersion(config_hash=h, content=settings.canonical()))
        session.flush()
    return h


def lineage(trigger: str) -> list[str]:
    """Replay scans form their own history; manual and scheduled scans share one."""
    return ["replay"] if trigger == "replay" else ["manual", "schedule"]


def fmt_pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:+.1f}%"


def format_summary(product: str, attention: str, n_sources: int, signal_start: date | None, price: str,
                   relative_return: float | None, benchmark: str | None, retail: str, days_to_earnings: int | None,
                   earnings_status: str, as_of: date) -> str:
    """The one-line summary: "{product}: attention {status} ({n} sources, {days} days), price ..."."""
    days = (as_of - signal_start).days + 1 if signal_start else 0
    dte = days_to_earnings if earnings_status != "unknown" else "unknown"
    return (f"{product}: attention {attention} ({n_sources} source{'' if n_sources == 1 else 's'}, {days} days), "
            f"price {price} ({fmt_pct(relative_return)} vs {benchmark or 'benchmark'}), "
            f"retail {retail}, {dte} days to earnings.")


def summary_line(product: str, att: AttentionResult, price: PriceResult, retail: RetailResult,
                 earn: EarningsResult, as_of: date) -> str:
    return format_summary(product, att.status, att.n_accelerating, att.signal_start_date, price.status,
                          price.components.get("relative_return"), price.components.get("benchmark"),
                          retail.status, earn.days_to_earnings, earn.status, as_of)


def _announcements(session: Session, as_of: date, days: int) -> dict[tuple[int, int | None], list[dict]]:
    rows = session.scalars(select(Announcement).where(
        Announcement.event_date <= as_of, Announcement.event_date >= as_of - timedelta(days=days)))
    out: dict = {}
    for a in rows:
        out.setdefault(a.company_id, []).append(
            {"id": a.id, "product_id": a.product_id, "event_date": a.event_date.isoformat(), "type": a.type,
             "title": a.title})
    return out


def compute_company(view: AsOfView, company: Company, settings: Settings) -> dict:
    fam = settings.families
    close, _ = view.series(fam.price.close.source, company.ticker, fam.price.close.metric)
    volume, _ = view.series(fam.price.volume.source, company.ticker, fam.price.volume.metric)
    bench, _ = view.series(fam.price.close.source, company.benchmark_ticker, fam.price.close.metric)
    retail_inputs = []
    for ref in fam.retail:
        s, info = view.series(ref.source, company.ticker, ref.metric)
        breadth = view.series(ref.source, company.ticker, ref.breadth_metric)[0] if ref.breadth_metric else None
        retail_inputs.append(RetailInput(ref.source, ref.metric, s, info, ref.sparse_floor, ref.breadth_metric, breadth))
    return {"close": close, "volume": volume, "bench": bench,
            "retail": compute_retail(retail_inputs, view.as_of, settings),
            "earnings": compute_earnings(view, company, settings)}


def compute_product(view: AsOfView, product: Product, company: Company, cdata: dict, settings: Settings) -> dict:
    inputs = []
    for ref in settings.families.attention:
        s, info = view.series(ref.source, str(product.id), ref.metric)
        inputs.append(SourceInput(ref.source, ref.metric, s, info, ref.sparse_floor))
    att = compute_attention(inputs, view.as_of, settings)
    price = compute_price(cdata["close"], cdata["volume"], cdata["bench"], company.benchmark_ticker, view.as_of,
                          att.signal_start_date, settings)
    retail: RetailResult = cdata["retail"]
    earn: EarningsResult = cdata["earnings"]
    stage, rule_idx = evaluate(StageInputs(view.as_of, att.status, price.status, retail.status, earn.status,
                                           att.last_elevated_date, earn.quarter_open), settings)
    rescaled = any(c.get("rescaled_history") for c in att.components.get("sources", {}).values()) or any(
        c.get("rescaled_history") for c in retail.components.get("sources", {}).values())
    return {"attention": att, "price": price, "retail": retail, "earnings": earn, "stage": stage,
            "rule_index": rule_idx, "rescaled_history": rescaled}


def input_health(r: dict) -> dict:
    def fam(sources: dict) -> dict:
        return {k: {"healthy": v.get("healthy"), "reason": v.get("reason"), "last_obs_date": v.get("last_obs_date")}
                for k, v in sources.items()}
    att, price, retail, earn = r["attention"], r["price"], r["retail"], r["earnings"]
    return {
        "attention": {"status": att.status, "reason": att.components.get("reason"),
                      "sources": fam(att.components.get("sources", {}))},
        "price": {"status": price.status, "reason": price.components.get("reason"),
                  "sources": {k: {"healthy": v["healthy"], "reason": v["reason"], "last_obs_date": v["last_obs_date"]}
                              for k, v in price.components.get("health", {}).items()}},
        "retail": {"status": retail.status, "reason": retail.components.get("reason"),
                   "sources": fam(retail.components.get("sources", {}))},
        "earnings": {"status": earn.status, "reason": earn.reason, "confirmed": earn.confirmed,
                     "next_earnings_date": earn.next_earnings_date.isoformat() if earn.next_earnings_date else None,
                     "fiscal_quarter_end": earn.fiscal_quarter_end.isoformat() if earn.fiscal_quarter_end else None},
        "flags": {"rescaled_history": r["rescaled_history"], "single_source": att.single_source,
                  "seasonal": att.status == "seasonal",
                  "quarter_closed": earn.quarter_open is False},
    }


def run_scan(session: Session, settings: Settings, as_of: date | None = None, trigger: str = "manual",
             repo: ObservationRepository | None = None) -> ScanResult:
    as_of = resolve_as_of(as_of)
    chash = ensure_config_version(session, settings)
    scan = Scan(as_of=as_of, trigger=trigger, config_hash=chash, status="running", started_at=utcnow())
    session.add(scan)
    session.commit()
    try:
        result = _scan_body(session, settings, scan, repo)
        scan.status, scan.finished_at = "ok", utcnow()
        session.commit()
        log.info("scan id=%s as_of=%s trigger=%s config=%s products=%d alerts=%d stages=%s", scan.id, as_of,
                 trigger, chash, result.products, result.alerts_created, result.stages)
        return result
    except Exception as e:
        session.rollback()
        scan = session.get(Scan, scan.id)
        scan.status, scan.finished_at, scan.error_message = "error", utcnow(), f"{type(e).__name__}: {e}"
        session.commit()
        log.exception("scan id=%s as_of=%s failed", scan.id, as_of)
        raise


def _scan_body(session: Session, settings: Settings, scan: Scan, repo: ObservationRepository | None) -> ScanResult:
    as_of = scan.as_of
    if repo is None:
        repo = ObservationRepository(session, since=as_of - timedelta(days=settings.demo.history_days + 400))
    view = repo.at(as_of)
    companies = session.scalars(select(Company).where(Company.active.is_(True))
                                .options(selectinload(Company.products)).order_by(Company.id)).all()
    anns = _announcements(session, as_of, settings.attention.announcement_lookback_days)

    prior = session.scalar(select(Scan).where(Scan.as_of < as_of, Scan.status == "ok",
                                              Scan.trigger.in_(lineage(scan.trigger)))
                           .order_by(Scan.as_of.desc(), Scan.id.desc()).limit(1))
    prior_states = {s.product_id: s for s in session.scalars(
        select(SignalState).where(SignalState.scan_id == prior.id))} if prior else {}

    stages: Counter = Counter()
    alerts = 0
    n_products = 0
    for company in companies:
        cdata = compute_company(view, company, settings)
        for product in sorted(company.products, key=lambda p: p.id):
            if not product.active:
                continue
            n_products += 1
            r = compute_product(view, product, company, cdata, settings)
            att, price, retail, earn = r["attention"], r["price"], r["retail"], r["earnings"]
            att.components["announcements"] = [a for a in anns.get(company.id, [])
                                               if a["product_id"] in (None, product.id)]
            state = SignalState(
                scan_id=scan.id, product_id=product.id, attention_status=att.status, attention_score=att.score,
                attention_components=att.components, price_response=price.status, price_components=price.components,
                retail_status=retail.status, retail_components=retail.components,
                signal_start_date=att.signal_start_date, days_to_earnings=earn.days_to_earnings,
                days_left_in_quarter=earn.days_left_in_quarter, stage=r["stage"], input_health=input_health(r))
            session.add(state)
            stages[r["stage"]] += 1
            if maybe_alert(session, settings, scan, company, product, state, prior_states.get(product.id), r):
                alerts += 1
    session.flush()
    return ScanResult(scan.id, as_of, scan.trigger, scan.config_hash, n_products, dict(stages), alerts)


def maybe_alert(session: Session, settings: Settings, scan: Scan, company: Company, product: Product,
                state: SignalState, prior: SignalState | None, r: dict) -> bool:
    """One alert per transition: a reportable stage that is new, or whose price/retail status changed."""
    if state.stage not in settings.reportable_stages:
        return False
    changed = []
    for fld, _label in TRACKED_FIELDS:
        before = getattr(prior, fld) if prior else None
        after = getattr(state, fld)
        if before != after:
            changed.append({"field": fld, "from": before, "to": after})
    if prior is not None and not changed:
        return False

    # Re-running a scan for the same date and config must not duplicate the alert.
    dup = session.scalars(select(Alert).join(Scan, Scan.id == Alert.scan_id).where(
        Alert.product_id == product.id, Alert.as_of == scan.as_of, Alert.config_hash == scan.config_hash,
        Alert.stage == state.stage, Scan.trigger.in_(lineage(scan.trigger)))).all()
    for a in dup:
        snap = a.input_snapshot
        if snap.get("price", {}).get("status") == state.price_response and \
                snap.get("retail", {}).get("status") == state.retail_status:
            return False

    att, price, retail, earn = r["attention"], r["price"], r["retail"], r["earnings"]
    snapshot = {
        "as_of": scan.as_of.isoformat(), "trigger": scan.trigger, "scan_id": scan.id,
        "company": {"id": company.id, "ticker": company.ticker, "name": company.name,
                    "benchmark": company.benchmark_ticker},
        "product": {"id": product.id, "name": product.name},
        "stage": state.stage, "rule_index": r["rule_index"],
        "rule": settings.stages[r["rule_index"]].model_dump(mode="json") if r["rule_index"] is not None else None,
        "attention": {"status": att.status, "score": att.score,
                      "signal_start_date": att.signal_start_date.isoformat() if att.signal_start_date else None,
                      "last_elevated_date": att.last_elevated_date.isoformat() if att.last_elevated_date else None,
                      "components": att.components},
        "price": {"status": price.status, "components": price.components},
        "retail": {"status": retail.status, "components": retail.components},
        "earnings": earn.as_dict(),
        "input_health": state.input_health,
    }
    session.add(Alert(scan_id=scan.id, as_of=scan.as_of, product_id=product.id, company_id=company.id,
                      stage=state.stage, prior_stage=prior.stage if prior else None, changed_fields=changed,
                      summary=summary_line(product.name, att, price, retail, earn, scan.as_of),
                      input_snapshot=_jsonable(snapshot), config_hash=scan.config_hash))
    return True


def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (date, pd.Timestamp)):
        return x.isoformat()
    return x
