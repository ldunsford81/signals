"""`socialarb seed`: create the database, run migrations, load the demo catalog and demo observations."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import calendar
from app.core.config import Settings
from app.core.logging import get_logger
from app.core.paths import database_file
from app.db.models import Announcement, Company, Product
from app.db.session import get_engine, session_factory, upgrade_db
from app.pipeline.ingest import RunSummary, run_ingest
from app.sources.demo import state
from app.sources.demo.universe import ANNOUNCEMENTS, COMPANIES

log = get_logger("seed")


class SeedError(Exception):
    pass


def load_catalog(session: Session, anchor: date) -> int:
    added = 0
    for spec in COMPANIES:
        c = session.scalar(select(Company).where(Company.ticker == spec.ticker))
        if c is None:
            c = Company(ticker=spec.ticker)
            session.add(c)
            added += 1
        c.name, c.exchange, c.sector, c.is_demo = spec.name, spec.exchange, spec.sector, spec.is_demo
        c.market_cap_usd_m, c.analyst_count, c.benchmark_ticker = spec.market_cap_usd_m, spec.analyst_count, spec.benchmark
        c.cashtag_exclusions = c.cashtag_exclusions or []
        c.notes = spec.notes or f"Demo scenario {spec.scenario}. Numbers are synthetic."
        c.active = True
        session.flush()
        existing = {p.name for p in c.products}
        for p in spec.products:
            if p.name not in existing:
                session.add(Product(company_id=c.id, name=p.name, keywords=list(p.keywords),
                                    launched_on=anchor + timedelta(days=p.launched_offset), active=True))
    session.flush()
    for ticker, idx, offset, kind, title in ANNOUNCEMENTS:
        c = session.scalar(select(Company).where(Company.ticker == ticker))
        if c is None or session.scalar(select(Announcement).where(Announcement.company_id == c.id,
                                                                  Announcement.title == title)):
            continue
        products = session.scalars(select(Product).where(Product.company_id == c.id).order_by(Product.id)).all()
        product = products[idx] if idx is not None else None
        session.add(Announcement(company_id=c.id, product_id=product.id if product else None,
                                 event_date=anchor + timedelta(days=offset), type=kind, title=title,
                                 notes="Demo announcement (synthetic)."))
    session.commit()
    return added


def seed(settings: Settings, reset: bool = False) -> tuple[date, list[RunSummary]]:
    db = database_file()
    if reset:
        get_engine.cache_clear()
        if db and db.exists():
            for suffix in ("", "-wal", "-shm"):
                db.with_name(db.name + suffix).unlink(missing_ok=True)
        state._state_file().unlink(missing_ok=True)
    upgrade_db()

    s = session_factory()()
    try:
        has_data = (s.scalar(select(func.count()).select_from(Company)) or 0) > 0
        stored = state.stored_anchor() if has_data else None
        if settings.demo.anchor_date:
            anchor = calendar.session_on_or_before(settings.demo.anchor_date)
        else:
            anchor = stored or calendar.last_completed_session()
        if stored and stored != anchor:
            raise SeedError(f"Database was seeded with anchor {stored}; config asks for {anchor}. "
                            "Run `socialarb seed --reset` to rebuild the demo.")
        state.store_anchor(anchor)
        load_catalog(s, anchor)
        log.info("seeding demo history anchored to %s", anchor)
        runs = run_ingest(s, settings, as_of=anchor, full_history=True)
        return anchor, runs
    finally:
        s.close()
