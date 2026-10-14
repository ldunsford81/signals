"""Read model for the Review feed, and the one write the review screens make (alert_reviews).

The feed shows every product in a reportable stage at the latest (non-replay) scan, grouped by
company, ordered like the watchlist. Products that stay in a stage keep appearing here from
signal_states even though no new alert is written. data_gap products go to a health panel.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Alert, AlertReview, Company, ConfigVersion, Product, Scan, SignalState
from app.pipeline.scan import format_summary, lineage, prior_scan
from app.stages.engine import describe

DECISIONS = ("unreviewed", "acted", "passed", "exited")
TRACKED = [("stage", "stage", "Stage"), ("attention_status", "attention", "Attention"),
           ("price_response", "price", "Price"), ("retail_status", "retail", "Retail")]


class FeedError(Exception):
    pass


def _scan_settings(session: Session, scan: Scan, current: Settings) -> Settings:
    """The config that produced this scan (rules may have changed since)."""
    if scan.config_hash == current.hash():
        return current
    cv = session.scalar(select(ConfigVersion).where(ConfigVersion.config_hash == scan.config_hash))
    return Settings.model_validate(cv.content) if cv else current


def latest_review(session: Session, alert_id: int) -> AlertReview | None:
    return session.scalar(select(AlertReview).where(AlertReview.alert_id == alert_id)
                          .order_by(AlertReview.reviewed_at.desc(), AlertReview.id.desc()).limit(1))


def _changes(state: SignalState, prior: SignalState | None) -> list[dict]:
    if prior is None:
        return []
    out = []
    for attr, key, label in TRACKED:
        a, b = getattr(prior, attr), getattr(state, attr)
        if a != b:
            out.append({"field": key, "label": label, "from": a, "to": b})
    return out


def _unknown_inputs(health: dict) -> list[dict]:
    out = []
    for fam in ("attention", "price", "retail", "earnings"):
        h = health.get(fam, {})
        if h.get("status") == "unknown":
            reason = h.get("reason")
            if not reason:
                bad = [f"{k}: {v.get('reason')}" for k, v in h.get("sources", {}).items() if not v.get("healthy")]
                reason = "; ".join(bad) or "unknown"
            out.append({"family": fam, "reason": reason.removeprefix(f"{fam}: ")})
    return out


def build_feed(session: Session, settings: Settings, scan_id: int | None = None) -> dict:
    q = select(Scan).where(Scan.status == "ok")
    q = q.where(Scan.id == scan_id) if scan_id else q.where(Scan.trigger != "replay")
    scan = session.scalar(q.order_by(Scan.as_of.desc(), Scan.id.desc()).limit(1))
    if scan is None:
        return {"scan": None, "prior_as_of": None, "groups": [], "health": [], "counts": {}}

    cfg = _scan_settings(session, scan, settings)
    rules = {r.name: r for r in cfg.stages}
    rank = {s: i for i, s in enumerate(cfg.stage_priority)}
    prior = prior_scan(session, scan)
    prior_states = {s.product_id: s for s in session.scalars(
        select(SignalState).where(SignalState.scan_id == prior.id))} if prior else {}

    rows = session.execute(
        select(SignalState, Product, Company).join(Product, Product.id == SignalState.product_id)
        .join(Company, Company.id == Product.company_id).where(SignalState.scan_id == scan.id)).all()

    cards, health = [], []
    for st, p, c in rows:
        ih = st.input_health or {}
        earn = ih.get("earnings", {})
        if st.stage == "data_gap":
            health.append({"product_id": p.id, "product": p.name, "company": c.name, "ticker": c.ticker,
                           "attention": st.attention_status, "signal_start_date": st.signal_start_date,
                           "unknown_inputs": _unknown_inputs(ih), "reason": describe(rules["data_gap"], cfg)
                           if "data_gap" in rules else None})
            continue
        if st.stage not in cfg.reportable_stages:
            continue
        pc, ac = st.price_components or {}, st.attention_components or {}
        # The alert this card belongs to: the latest one for this product in this stage, this lineage.
        alert = session.scalar(
            select(Alert).join(Scan, Scan.id == Alert.scan_id)
            .where(Alert.product_id == p.id, Alert.stage == st.stage, Alert.as_of <= scan.as_of,
                   Scan.trigger.in_(lineage(scan.trigger)))
            .order_by(Alert.as_of.desc(), Alert.id.desc()).limit(1))
        review = latest_review(session, alert.id) if alert else None
        prior_state = prior_states.get(p.id)
        cards.append({
            "product_id": p.id, "product": p.name, "company_id": c.id, "company": c.name, "ticker": c.ticker,
            "is_demo": c.is_demo, "stage": st.stage,
            "summary": format_summary(p.name, st.attention_status, len(ac.get("accelerating_sources", [])),
                                      st.signal_start_date, st.price_response, pc.get("relative_return"),
                                      pc.get("benchmark"), st.retail_status, st.days_to_earnings,
                                      earn.get("status", "unknown"), scan.as_of),
            "reason": describe(rules[st.stage], cfg) if st.stage in rules else None,
            "attention": st.attention_status, "attention_score": st.attention_score,
            "single_source": bool(ih.get("flags", {}).get("single_source")),
            "price": st.price_response, "relative_return": pc.get("relative_return"),
            "volume_ratio": pc.get("volume_ratio"), "benchmark": pc.get("benchmark"),
            "retail": st.retail_status, "signal_start_date": st.signal_start_date,
            "days_to_earnings": st.days_to_earnings, "earnings_projected": earn.get("confirmed") is False,
            "earnings_status": earn.get("status", "unknown"), "days_left_in_quarter": st.days_left_in_quarter,
            "quarter_closed": bool(ih.get("flags", {}).get("quarter_closed")),
            "is_new": prior is None or prior_state is None or prior_state.stage != st.stage,
            "changes": _changes(st, prior_state),
            "alert_id": alert.id if alert else None,
            "alert_as_of": alert.as_of if alert else None,
            "decision": review.decision if review else "unreviewed",
            "note": review.note if review else None,
            "reviewed_at": review.reviewed_at if review else None,
        })

    def key(card):
        return (rank.get(card["stage"], len(rank)), -(card["attention_score"] or float("-inf")), card["product"])

    cards.sort(key=key)
    groups: dict[int, dict] = {}
    for card in cards:  # first card per company is its strongest product
        g = groups.setdefault(card["company_id"], {"company_id": card["company_id"], "company": card["company"],
                                                   "ticker": card["ticker"], "is_demo": card["is_demo"], "cards": []})
        g["cards"].append(card)
    counts: dict[str, int] = {}
    for card in cards:
        counts[card["stage"]] = counts.get(card["stage"], 0) + 1
    health.sort(key=lambda h: (h["ticker"], h["product"]))
    return {"scan": {"id": scan.id, "as_of": scan.as_of, "trigger": scan.trigger, "config_hash": scan.config_hash,
                     "finished_at": scan.finished_at},
            "prior_as_of": prior.as_of if prior else None, "groups": list(groups.values()),
            "health": health, "counts": counts}


def record_review(session: Session, alert_id: int, decision: str, note: str | None) -> AlertReview:
    """Append a review row. Reviews are a log: the latest row is the current decision; alerts are untouched."""
    if decision not in DECISIONS:
        raise FeedError(f"decision must be one of {', '.join(DECISIONS)}")
    if session.get(Alert, alert_id) is None:
        raise FeedError(f"alert {alert_id} not found")
    r = AlertReview(alert_id=alert_id, decision=decision, note=(note or "").strip() or None)
    session.add(r)
    session.commit()
    return r


def review_history(session: Session, alert_id: int) -> list[AlertReview]:
    return list(session.scalars(select(AlertReview).where(AlertReview.alert_id == alert_id)
                                .order_by(AlertReview.reviewed_at.desc(), AlertReview.id.desc())))
