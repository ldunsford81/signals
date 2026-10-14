"""Admin: the hand-maintained catalog (companies, products, announcements), CSV import, and flags.

Earnings dates edited here are also written as point-in-time observations under the
`earnings_manual` source, so the scan sees them from today on (and replay before today does not).
"""
from __future__ import annotations

import csv
import io
from datetime import date

from sqlalchemy import and_, delete, insert, select
from sqlalchemy.orm import Session

from app.core import calendar
from app.core.config import Settings
from app.db.models import Announcement, Company, Observation, Product, Scan, utcnow
from app.signals.earnings import MANUAL_SOURCE, compute_earnings
from app.signals.store import ObservationRepository
from app.sources.base import date_to_value

ANNOUNCEMENT_TYPES = ("new_product", "partnership", "distribution", "negative_event", "other")
COMPANY_FIELDS = ("ticker", "name", "exchange", "sector", "is_demo", "market_cap_usd_m", "analyst_count",
                  "benchmark_ticker", "next_earnings_date", "earnings_date_confirmed", "fiscal_quarter_end",
                  "cashtag_exclusions", "active", "notes")
EARNINGS_FIELDS = ("next_earnings_date", "earnings_date_confirmed", "fiscal_quarter_end")


class AdminError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def effective_date(session: Session) -> date:
    """'Today' for the catalog: the latest live scan date, or the last completed session."""
    latest = session.scalar(select(Scan.as_of).where(Scan.status == "ok", Scan.trigger != "replay")
                            .order_by(Scan.as_of.desc()).limit(1))
    return latest or calendar.last_completed_session()


# ---- companies ----------------------------------------------------------------------
def company_dict(c: Company, earnings: dict | None = None) -> dict:
    out = {f: getattr(c, f) for f in COMPANY_FIELDS}
    out.update(id=c.id, product_count=len(c.products), earnings=earnings)
    return out


def earnings_flags(session: Session, settings: Settings) -> dict[int, dict]:
    """What the scan would see for each company's earnings today."""
    as_of = effective_date(session)
    view = ObservationRepository(session, sources=["earnings", MANUAL_SOURCE]).at(as_of)
    out = {}
    for c in session.scalars(select(Company)):
        e = compute_earnings(view, c, settings)
        out[c.id] = {"as_of": as_of, "status": e.status, "reason": e.reason, "source": e.source,
                     "next_earnings_date": e.next_earnings_date, "confirmed": e.confirmed,
                     "fiscal_quarter_end": e.fiscal_quarter_end, "days_to_earnings": e.days_to_earnings,
                     "needs_date_update": e.status == "unknown"}
    return out


def list_companies(session: Session, settings: Settings) -> list[dict]:
    flags = earnings_flags(session, settings)
    rows = session.scalars(select(Company).order_by(Company.ticker)).all()
    out = [company_dict(c, flags.get(c.id)) for c in rows]
    out.sort(key=lambda c: (not (c["earnings"] or {}).get("needs_date_update"), not c["active"], c["ticker"]))
    return out


def _write_manual_earnings(session: Session, c: Company) -> None:
    if c.next_earnings_date is None:
        return
    d = effective_date(session)
    values = {"next_earnings_date": date_to_value(c.next_earnings_date),
              "confirmed": float(bool(c.earnings_date_confirmed))}
    if c.fiscal_quarter_end:
        values["fiscal_quarter_end"] = date_to_value(c.fiscal_quarter_end)
    session.execute(delete(Observation).where(and_(Observation.source == MANUAL_SOURCE,
                                                   Observation.entity_key == c.ticker, Observation.obs_date == d)))
    session.execute(insert(Observation), [
        dict(source=MANUAL_SOURCE, entity_type="company", entity_key=c.ticker, metric=m, obs_date=d, value=v,
             snapshot_id=None, ingested_at=utcnow()) for m, v in values.items()])


def _apply_company(session: Session, c: Company, data: dict) -> None:
    before = {f: getattr(c, f) for f in EARNINGS_FIELDS}
    for f in COMPANY_FIELDS:
        if f in data:
            setattr(c, f, data[f])
    c.ticker = c.ticker.strip().upper()
    c.benchmark_ticker = (c.benchmark_ticker or "XLY").strip().upper()
    if c.cashtag_exclusions is None:
        c.cashtag_exclusions = []
    if any(getattr(c, f) != before[f] for f in EARNINGS_FIELDS):
        session.flush()
        _write_manual_earnings(session, c)


def create_company(session: Session, data: dict) -> Company:
    ticker = (data.get("ticker") or "").strip().upper()
    if not ticker:
        raise AdminError("ticker is required")
    if session.scalar(select(Company).where(Company.ticker == ticker)):
        raise AdminError(f"company {ticker} already exists", 409)
    c = Company(ticker=ticker, name=data.get("name") or ticker, cashtag_exclusions=[])
    session.add(c)
    _apply_company(session, c, data)
    session.commit()
    return c


def update_company(session: Session, company_id: int, data: dict) -> Company:
    c = session.get(Company, company_id)
    if c is None:
        raise AdminError(f"company {company_id} not found", 404)
    new_ticker = (data.get("ticker") or c.ticker).strip().upper()
    if new_ticker != c.ticker:
        raise AdminError("ticker cannot be changed (observations and alerts are keyed on it); "
                         "deactivate this company and add a new one")
    _apply_company(session, c, data)
    session.commit()
    return c


# ---- products ---------------------------------------------------------------------------
def product_dict(p: Product) -> dict:
    return {"id": p.id, "company_id": p.company_id, "ticker": p.company.ticker, "name": p.name,
            "keywords": p.keywords or [], "launched_on": p.launched_on, "active": p.active}


def list_products(session: Session, company_id: int | None = None) -> list[dict]:
    q = select(Product).join(Company)
    if company_id:
        q = q.where(Product.company_id == company_id)
    return [product_dict(p) for p in session.scalars(q.order_by(Company.ticker, Product.id))]


def _clean_keywords(kw) -> list[str]:
    if isinstance(kw, str):
        kw = kw.replace(";", ",").split(",")
    return [k.strip() for k in (kw or []) if k and k.strip()]


def create_product(session: Session, data: dict) -> Product:
    c = session.get(Company, data.get("company_id"))
    if c is None:
        raise AdminError("company not found", 404)
    name = (data.get("name") or "").strip()
    if not name:
        raise AdminError("product name is required")
    if session.scalar(select(Product).where(Product.company_id == c.id, Product.name == name)):
        raise AdminError(f"{c.ticker} already has a product called '{name}'", 409)
    p = Product(company_id=c.id, name=name, keywords=_clean_keywords(data.get("keywords")) or [name.lower()],
                launched_on=data.get("launched_on"), active=data.get("active", True))
    session.add(p)
    session.commit()
    return p


def update_product(session: Session, product_id: int, data: dict) -> Product:
    p = session.get(Product, product_id)
    if p is None:
        raise AdminError(f"product {product_id} not found", 404)
    if "name" in data and data["name"] and data["name"].strip() != p.name:
        raise AdminError("product names cannot be changed (the demo series and history follow the name); "
                         "deactivate it and add a new one")
    if "keywords" in data:
        p.keywords = _clean_keywords(data["keywords"])
    for f in ("launched_on", "active"):
        if f in data:
            setattr(p, f, data[f])
    session.commit()
    return p


# ---- announcements ------------------------------------------------------------------------
def announcement_dict(a: Announcement, ticker: str) -> dict:
    return {"id": a.id, "company_id": a.company_id, "ticker": ticker, "product_id": a.product_id,
            "event_date": a.event_date, "type": a.type, "title": a.title, "url": a.url, "notes": a.notes}


def list_announcements(session: Session) -> list[dict]:
    rows = session.execute(select(Announcement, Company.ticker).join(Company)
                           .order_by(Announcement.event_date.desc(), Announcement.id.desc())).all()
    return [announcement_dict(a, t) for a, t in rows]


def _apply_announcement(session: Session, a: Announcement, data: dict) -> None:
    for f in ("company_id", "product_id", "event_date", "type", "title", "url", "notes"):
        if f in data:
            setattr(a, f, data[f])
    c = session.get(Company, a.company_id)
    if c is None:
        raise AdminError("company not found", 404)
    if a.product_id is not None:
        p = session.get(Product, a.product_id)
        if p is None or p.company_id != c.id:
            raise AdminError("product does not belong to that company")
    if a.type not in ANNOUNCEMENT_TYPES:
        raise AdminError(f"type must be one of {', '.join(ANNOUNCEMENT_TYPES)}")
    if not (a.title or "").strip():
        raise AdminError("title is required")


def create_announcement(session: Session, data: dict) -> dict:
    a = Announcement()
    _apply_announcement(session, a, data)
    session.add(a)
    session.commit()
    return announcement_dict(a, session.get(Company, a.company_id).ticker)


def update_announcement(session: Session, ann_id: int, data: dict) -> dict:
    a = session.get(Announcement, ann_id)
    if a is None:
        raise AdminError(f"announcement {ann_id} not found", 404)
    _apply_announcement(session, a, data)
    session.commit()
    return announcement_dict(a, session.get(Company, a.company_id).ticker)


def delete_announcement(session: Session, ann_id: int) -> None:
    a = session.get(Announcement, ann_id)
    if a is None:
        raise AdminError(f"announcement {ann_id} not found", 404)
    session.delete(a)
    session.commit()


# ---- CSV import -----------------------------------------------------------------------------
COMPANY_CSV_COLUMNS = ["ticker", "name", "exchange", "sector", "benchmark_ticker", "market_cap_usd_m",
                       "analyst_count", "next_earnings_date", "earnings_date_confirmed", "fiscal_quarter_end",
                       "is_demo", "active", "notes"]
PRODUCT_CSV_COLUMNS = ["ticker", "name", "keywords", "launched_on", "active"]

_TRUE = {"1", "true", "yes", "y", "t"}
_FALSE = {"0", "false", "no", "n", "f", ""}


def _bool(v: str, default: bool) -> bool:
    v = (v or "").strip().lower()
    if v == "":
        return default
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    raise ValueError(f"'{v}' is not true/false")


def _date(v: str) -> date | None:
    v = (v or "").strip()
    return date.fromisoformat(v) if v else None


def _num(v: str, kind=float):
    v = (v or "").strip().replace(",", "")
    return kind(v) if v else None


def _rows(text: str, required: list[str]) -> list[tuple[int, dict]]:
    reader = csv.DictReader(io.StringIO(text.strip().lstrip("﻿")))
    cols = [c.strip().lower() for c in (reader.fieldnames or [])]
    missing = [c for c in required if c not in cols]
    if missing:
        raise AdminError(f"CSV is missing column(s): {', '.join(missing)}")
    out = []
    for i, raw in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        if any(row.values()):
            out.append((i, row))
    return out


def import_companies(session: Session, text: str, dry_run: bool = False) -> dict:
    rows = _rows(text, ["ticker", "name"])
    parsed, errors = [], []
    for line, r in rows:
        try:
            if not r["ticker"]:
                raise ValueError("ticker is empty")
            data = {"ticker": r["ticker"].upper(), "name": r["name"] or r["ticker"].upper()}
            for f in ("exchange", "sector", "notes"):
                if r.get(f):
                    data[f] = r[f]
            if r.get("benchmark_ticker"):
                data["benchmark_ticker"] = r["benchmark_ticker"].upper()
            if "market_cap_usd_m" in r:
                data["market_cap_usd_m"] = _num(r["market_cap_usd_m"])
            if "analyst_count" in r:
                data["analyst_count"] = _num(r["analyst_count"], int)
            for f in ("next_earnings_date", "fiscal_quarter_end"):
                if r.get(f):
                    data[f] = _date(r[f])
            if "earnings_date_confirmed" in r:
                data["earnings_date_confirmed"] = _bool(r["earnings_date_confirmed"], False)
            if "is_demo" in r:
                data["is_demo"] = _bool(r["is_demo"], False)
            if "active" in r:
                data["active"] = _bool(r["active"], True)
            parsed.append((line, data))
        except ValueError as e:
            errors.append({"line": line, "error": str(e)})
    if errors:
        return {"created": 0, "updated": 0, "errors": errors, "applied": False}
    created = updated = 0
    for _, data in parsed:
        c = session.scalar(select(Company).where(Company.ticker == data["ticker"]))
        if c is None:
            c = Company(ticker=data["ticker"], name=data["name"], cashtag_exclusions=[])
            session.add(c)
            created += 1
        else:
            updated += 1
        _apply_company(session, c, data)
    if dry_run:
        session.rollback()
    else:
        session.commit()
    return {"created": created, "updated": updated, "errors": [], "applied": not dry_run}


def import_products(session: Session, text: str, dry_run: bool = False) -> dict:
    rows = _rows(text, ["ticker", "name"])
    companies = {c.ticker: c for c in session.scalars(select(Company))}
    parsed, errors = [], []
    for line, r in rows:
        try:
            c = companies.get(r["ticker"].upper())
            if c is None:
                raise ValueError(f"unknown ticker '{r['ticker']}' (import companies first)")
            if not r["name"]:
                raise ValueError("name is empty")
            parsed.append((c, {"name": r["name"], "keywords": _clean_keywords(r.get("keywords", "")),
                               "launched_on": _date(r.get("launched_on", "")),
                               "active": _bool(r.get("active", ""), True)}))
        except ValueError as e:
            errors.append({"line": line, "error": str(e)})
    if errors:
        return {"created": 0, "updated": 0, "errors": errors, "applied": False}
    created = updated = 0
    for c, data in parsed:
        p = session.scalar(select(Product).where(Product.company_id == c.id, Product.name == data["name"]))
        if p is None:
            session.add(Product(company_id=c.id, name=data["name"], keywords=data["keywords"] or [data["name"].lower()],
                                launched_on=data["launched_on"], active=data["active"]))
            created += 1
        else:
            if data["keywords"]:
                p.keywords = data["keywords"]
            p.launched_on = data["launched_on"] or p.launched_on
            p.active = data["active"]
            updated += 1
    if dry_run:
        session.rollback()
    else:
        session.commit()
    return {"created": created, "updated": updated, "errors": [], "applied": not dry_run}
