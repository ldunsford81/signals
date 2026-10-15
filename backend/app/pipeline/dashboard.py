"""Read models for the operator views: the Dashboard (one row per ticker) and the Ticker page.

These only reshape what the scan already stored (signal_states, alerts, reviews) plus short
point-in-time series for sparklines. No rule is evaluated here.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Alert, Company, Product, Scan, SignalState, SourceRun
from app.pipeline import narrative as nv
from app.pipeline.detail import NotFound, product_detail
from app.pipeline.feed import latest_review
from app.pipeline.scan import lineage
from app.signals.health import num, window_stats
from app.signals.store import ObservationRepository

SPARK_DAYS = 45


def latest_live_scan(session: Session) -> Scan | None:
    return session.scalar(select(Scan).where(Scan.status == "ok", Scan.trigger != "replay")
                          .order_by(Scan.as_of.desc(), Scan.id.desc()).limit(1))


def _days(as_of: date, start: date | None) -> int | None:
    return (as_of - start).days + 1 if start else None


def _unknown_reasons(ih: dict) -> list[str]:
    out = []
    for fam, word in (("price", "price"), ("retail", "retail chatter"), ("earnings", "earnings")):
        h = ih.get(fam) or {}
        if h.get("status") == "unknown":
            r = nv.friendly_reason((h.get("reason") or "unknown").split("; ")[0].removeprefix("price: "))
            out.append(f"{word} {r}")
    return out


def _buzz_spark(view, settings: Settings, product_id: int, components: dict, as_of: date) -> list[float | None]:
    """Short-window mean of the strongest healthy attention source, indexed to 100 at the window start."""
    srcs = components.get("sources") or {}
    best = max((s for s in srcs.values() if s.get("healthy")), key=lambda s: s.get("ratio") or 0, default=None)
    if best is None:
        best = next(iter(srcs.values()), None)
    if best is None:
        return []
    series, _ = view.series(best["source"], str(product_id), best["metric"])
    st = window_stats(series, as_of, settings.attention.short_window, tuple(settings.attention.baseline_window))
    if st.empty:
        return []
    sm = st["short_mean"].loc[pd.Timestamp(as_of - timedelta(days=SPARK_DAYS - 1)):]
    base = sm.dropna().head(10).mean()
    if not base or pd.isna(base):
        return []
    return [num(v / base * 100) for v in sm]


def _rel_spark(view, settings: Settings, ticker: str, bench: str, as_of: date) -> list[float | None]:
    """Stock relative to its benchmark over the same window, indexed to 100 at the first session."""
    fam = settings.families.price.close
    c, _ = view.series(fam.source, ticker, fam.metric)
    b, _ = view.series(fam.source, bench, fam.metric)
    start = pd.Timestamp(as_of - timedelta(days=SPARK_DAYS - 1))
    c, b = c.loc[start:], b.loc[start:]
    if c.empty or b.empty:
        return []
    df = pd.concat([c, b], axis=1, keys=["c", "b"]).dropna()
    if df.empty:
        return []
    rel = (df["c"] / df["c"].iloc[0]) / (df["b"] / df["b"].iloc[0]) * 100
    return [num(v) for v in rel]


def _row(st: SignalState, p: Product, c: Company, as_of: date, new_ids: set[int]) -> dict:
    ac, pc, ih = st.attention_components or {}, st.price_components or {}, st.input_health or {}
    earn = ih.get("earnings") or {}
    n_ok, n_all = nv.healthy_sources(ac)
    return {
        "ticker": c.ticker, "company": c.name, "short_name": nv.short_name(c.name), "company_id": c.id,
        "is_demo": c.is_demo, "product_id": p.id, "product": p.name, "stage": st.stage,
        "label": nv.signal_label(st.stage, st.attention_status), "side": nv.SIGNAL.get(st.stage, {}).get("side"),
        "attention": st.attention_status, "buzz_ratio": nv.max_ratio(ac), "buzz_days": _days(as_of, st.signal_start_date),
        "sources_ok": n_ok, "sources_total": n_all, "strength": st.attention_score,
        "price": st.price_response, "relative_return": pc.get("relative_return"), "volume_ratio": pc.get("volume_ratio"),
        "benchmark": pc.get("benchmark") or c.benchmark_ticker, "retail": st.retail_status,
        "days_to_earnings": st.days_to_earnings, "earnings_status": earn.get("status", "unknown"),
        "earnings_projected": earn.get("confirmed") is False, "quarter_closed": bool((ih.get("flags") or {}).get("quarter_closed")),
        "single_source": bool((ih.get("flags") or {}).get("single_source")),
        "new_today": p.id in new_ids, "unknown_reasons": _unknown_reasons(ih),
    }


def _strongest(rows: list[dict], order: dict[str, int]) -> list[dict]:
    best: dict[str, dict] = {}
    for r in rows:
        k = r["ticker"]
        key = (order.get(r["stage"], 99), -(r["strength"] or -1e9))
        if k not in best or key < best[k]["_key"]:
            best[k] = {**r, "_key": key}
    out = sorted(best.values(), key=lambda r: (r["_key"], r["ticker"]))
    for r in out:
        r.pop("_key")
    return out


def _headline(rows: list[dict]) -> list[dict]:
    by = lambda s: [r for r in rows if r["stage"] == s]  # noqa: E731
    entry, early, exit_ = by("entry_review"), by("early_recognition"), by("exit_review")
    seg: list[dict] = []
    if entry:
        names = nv.join_names([r["short_name"] for r in entry])
        n_new = sum(r["new_today"] for r in entry)
        seg += [{"text": "Product buzz is running ahead of the stock at "}, {"text": names, "strong": True},
                {"text": f": {len(entry)} entry signal{'s' if len(entry) > 1 else ''}"
                         f"{f' ({n_new} new today)' if n_new else ''}. "}]
    if early:
        names = nv.join_names([r["short_name"] for r in early])
        seg += [{"text": names, "strong": True},
                {"text": f" {'is an early mover' if len(early) == 1 else 'are early movers'}: the price has started to follow. "}]
    if exit_:
        names = nv.join_names([r["short_name"] for r in exit_])
        seg += [{"text": names, "strong": True},
                {"text": f" {'has an exit signal' if len(exit_) == 1 else 'have exit signals'}: retail chatter has caught up with the buzz. "}]
    if not seg:
        seg = [{"text": "No entry or exit signals today. Nothing on the watchlist has product buzz running ahead of its stock."}]
    return seg


def _radar(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        ratio = f"{r['buzz_ratio']:.1f}×" if r["buzz_ratio"] else "up"
        if r["stage"] == "watch":
            why = (f"earnings are {r['days_to_earnings']} days out" if r["earnings_status"] == "outside_window"
                   else f"price already {nv.PRICE_WORD.get(r['price'], r['price']).lower()}")
            out.append({**r, "kind": "watch", "note": f"Buzz {ratio}, but {why}"})
        elif r["stage"] == "data_gap":
            out.append({**r, "kind": "gap", "note": f"Buzz {ratio}, but {(r['unknown_reasons'] or ['an input is missing'])[0]}"})
        elif r["earnings_status"] == "unknown":
            out.append({**r, "kind": "earnings", "label": "Needs date", "note": "Earnings date has passed: needs an update"})
        elif r["stage"] == "none" and r["retail"] in ("rising", "elevated"):
            out.append({**r, "kind": "chatter", "label": "Chatter", "note": "Retail chatter rising without product buzz"})
    return out


def _health(session: Session, settings: Settings, ref: date) -> dict:
    issues = []
    for name, cfg in settings.sources.items():
        if cfg.mode == "off":
            continue
        run = session.scalar(select(SourceRun).where(SourceRun.source == name).order_by(SourceRun.id.desc()).limit(1))
        good = session.scalar(select(SourceRun.last_good_obs_date).where(
            SourceRun.source == name, SourceRun.last_good_obs_date.is_not(None)).order_by(SourceRun.id.desc()).limit(1))
        limit = settings.health.max_staleness_days.get(name)
        if run is None:
            issues.append({"source": name, "message": "never run"})
        elif run.status in ("error", "partial", "skipped"):
            issues.append({"source": name, "message": f"{run.status}: {run.error_message or ''}".strip()})
        elif limit is not None and (good is None or (ref - good).days > limit):
            issues.append({"source": name, "message": f"stale since {good}"})
    return {"issues": issues, "ok": not issues}


def dashboard(session: Session, settings: Settings) -> dict:
    scan = latest_live_scan(session)
    if scan is None:
        return {"scan": None, "headline": [], "kpis": {}, "buy": [], "sell": [], "radar": [], "board": [],
                "health": _health(session, settings, date.today())}
    as_of = scan.as_of
    order = {s: i for i, s in enumerate(settings.stage_priority)}
    rows = session.execute(select(SignalState, Product, Company).join(Product, Product.id == SignalState.product_id)
                           .join(Company, Company.id == Product.company_id)
                           .where(SignalState.scan_id == scan.id, Company.active.is_(True))).all()
    new_ids = set(session.scalars(select(Alert.product_id).join(Scan, Scan.id == Alert.scan_id).where(
        Alert.as_of == as_of, Scan.trigger.in_(lineage(scan.trigger)))))
    all_rows = [_row(st, p, c, as_of, new_ids) for st, p, c in rows]
    board = _strongest(all_rows, order)

    view = ObservationRepository(session, since=as_of - timedelta(days=SPARK_DAYS + 70)).at(as_of)
    states = {st.product_id: st for st, _, _ in rows}
    for r in board:
        r["buzz_spark"] = _buzz_spark(view, settings, r["product_id"], states[r["product_id"]].attention_components or {}, as_of)
        r["price_spark"] = _rel_spark(view, settings, r["ticker"], r["benchmark"], as_of)
        r["products_in_signal"] = sum(1 for x in all_rows if x["ticker"] == r["ticker"] and x["side"] in ("buy", "sell"))

    count = lambda s: sum(1 for r in board if r["stage"] == s)  # noqa: E731
    new = lambda s: sum(1 for r in board if r["stage"] == s and r["new_today"])  # noqa: E731
    kpis = {"entry": {"count": count("entry_review"), "new": new("entry_review")},
            "early": {"count": count("early_recognition"), "new": new("early_recognition")},
            "exit": {"count": count("exit_review"), "new": new("exit_review")},
            "watch": {"count": count("watch"), "new": new("watch"),
                      "attention_needed": count("data_gap") + sum(1 for r in board if r["earnings_status"] == "unknown"
                                                                  and r["stage"] != "data_gap")}}
    return {
        "scan": {"id": scan.id, "as_of": as_of, "finished_at": scan.finished_at, "config_hash": scan.config_hash},
        "headline": _headline(board), "kpis": kpis,
        "buy": [r for r in board if r["side"] == "buy"],
        "sell": [r for r in board if r["side"] == "sell"],
        "radar": _radar(board), "board": board, "health": _health(session, settings, as_of),
    }


def ticker_view(session: Session, settings: Settings, ticker: str, product_id: int | None = None,
                days: int = 60) -> dict:
    company = session.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise NotFound(f"ticker {ticker} not found")
    scan = latest_live_scan(session)
    order = {s: i for i, s in enumerate(settings.stage_priority)}
    products = sorted([p for p in company.products if p.active], key=lambda p: p.id)
    states = {}
    if scan:
        states = {s.product_id: s for s in session.scalars(select(SignalState).where(
            SignalState.scan_id == scan.id, SignalState.product_id.in_([p.id for p in products])))}
    plist = []
    for p in products:
        st = states.get(p.id)
        plist.append({"id": p.id, "name": p.name, "stage": st.stage if st else "none",
                      "label": nv.signal_label(st.stage, st.attention_status) if st else "Not scanned",
                      "strength": st.attention_score if st else None})
    plist.sort(key=lambda x: (order.get(x["stage"], 99), -(x["strength"] or -1e9)))
    if product_id is None:
        product_id = plist[0]["id"] if plist else None
    if product_id is None:
        raise NotFound(f"{ticker} has no active products")

    d = product_detail(session, settings, product_id, days=days)
    out = {"company": d["company"], "products": plist, "product": d["product"], "scan": d["scan"],
           "announcements": d["announcements"], "history": d["history"][:30], "detail": d}
    st = d["state"]
    if st is None:
        out.update(signal=None)
        return out

    as_of = date.fromisoformat(d["scan"]["as_of"]) if isinstance(d["scan"]["as_of"], str) else d["scan"]["as_of"]
    ac, pc, rc, ih = st["attention_components"], st["price_components"], st["retail_components"], st["input_health"]
    earn = ih.get("earnings") or {}
    n_ok, n_all = nv.healthy_sources(ac)
    ratio = nv.max_ratio(ac)
    start = st["signal_start_date"]
    start_d = date.fromisoformat(start) if isinstance(start, str) else start
    sig_days = _days(as_of, start_d)
    retail_sources = rc.get("sources") or {}
    chatter_ratio = max((s.get("ratio") or 0 for s in retail_sources.values() if s.get("healthy")), default=None)

    # Decision: attached to the latest live alert for this product in its current stage.
    alert = session.scalar(select(Alert).join(Scan, Scan.id == Alert.scan_id).where(
        Alert.product_id == product_id, Alert.stage == st["stage"], Scan.trigger != "replay")
        .order_by(Alert.as_of.desc(), Alert.id.desc()).limit(1))
    review = latest_review(session, alert.id) if alert else None

    # Main chart: the strongest healthy attention source, and the stock relative to its benchmark.
    srcs = [s for s in d["attention_series"]]
    best_name = max(((k, v) for k, v in (ac.get("sources") or {}).items() if v.get("healthy")),
                    key=lambda kv: kv[1].get("ratio") or 0, default=(None, None))[0]
    buzz_series = next((s for s in srcs if s["source"] == best_name), srcs[0] if srcs else None)
    price_rel = [{"date": p["date"], "value": num((p["close"] / p["benchmark_rebased"] - 1) * 100)
                  if p["close"] and p["benchmark_rebased"] else None} for p in d["price_series"]]
    lo, hi = settings.earnings.window_days
    out.update(
        signal={
            "stage": st["stage"], "label": nv.signal_label(st["stage"], st["attention_status"]),
            "side": nv.SIGNAL.get(st["stage"], {}).get("side"), "since": alert.as_of if alert else None,
            "signal_start_date": start_d,
            "verdict": nv.verdict(d["product"]["name"], st["stage"], st["attention_status"], ratio, sig_days,
                                  st["price_response"], pc.get("relative_return"), pc.get("benchmark"),
                                  pc.get("volume_ratio"), st["retail_status"], st["days_to_earnings"],
                                  earn.get("status", "unknown"), _unknown_reasons(ih)),
            "checks": nv.checks(st["stage"], st["attention_status"], n_ok, n_all, st["price_response"],
                                pc.get("benchmark"), st["retail_status"], earn.get("status", "unknown"), (lo, hi)),
        },
        tiles={
            "buzz": {"status": nv.BUZZ_WORD.get(st["attention_status"], st["attention_status"]),
                     "raw": st["attention_status"], "ratio": ratio, "days": sig_days, "sources_ok": n_ok,
                     "sources_total": n_all, "single_source": bool((ih.get("flags") or {}).get("single_source")),
                     "seasonal": st["attention_status"] == "seasonal", "reason": ac.get("reason")},
            "price": {"status": nv.PRICE_WORD.get(st["price_response"], st["price_response"]), "raw": st["price_response"],
                      "relative_return": pc.get("relative_return"), "benchmark": pc.get("benchmark"),
                      "volume_ratio": pc.get("volume_ratio"), "anchor": pc.get("anchor_label"),
                      "base_date": pc.get("base_date"), "reason": pc.get("reason")},
            "chatter": {"status": nv.CHATTER_WORD.get(st["retail_status"], st["retail_status"]),
                        "raw": st["retail_status"], "ratio": chatter_ratio, "set_by": rc.get("set_by"),
                        "reason": rc.get("reason")},
        },
        earnings={"next_date": earn.get("next_earnings_date"), "days": st["days_to_earnings"],
                  "status": earn.get("status", "unknown"), "projected": earn.get("confirmed") is False,
                  "reason": earn.get("reason"), "quarter_end": earn.get("fiscal_quarter_end"),
                  "days_left_in_quarter": st["days_left_in_quarter"], "window": [lo, hi]},
        decision={"alert_id": alert.id if alert else None, "alert_as_of": alert.as_of if alert else None,
                  "decision": review.decision if review else "unreviewed", "note": review.note if review else None,
                  "reviewed_at": review.reviewed_at if review else None},
        chart={"buzz_source": buzz_series["source"] if buzz_series else None,
               "buzz": [{"date": p["date"], "value": p["short_mean"], "low": p["band_low"], "high": p["band_high"]}
                        for p in (buzz_series["points"] if buzz_series else [])],
               "price_rel": price_rel, "benchmark": pc.get("benchmark") or company.benchmark_ticker,
               "early_move": settings.price_response.early_move.min_relative_return,
               "clear_acceleration": settings.price_response.clear_acceleration.min_relative_return,
               "window_start": d["window_start"]},
    )
    return out
