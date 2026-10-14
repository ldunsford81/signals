"""Admin: catalog CRUD, manual earnings, CSV import, and add-a-product → daily → new alert."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import load_settings
from app.db.models import Observation
from app.db.session import session_factory
from app.main import app
from app.pipeline.scan import run_scan
from app.pipeline.seed import seed
from conftest import ANCHOR


@pytest.fixture()
def client(tmp_env, settings):
    seed(settings)                      # pins the demo anchor; the API then uses the plain config file
    with session_factory()() as s:
        run_scan(s, load_settings(), as_of=ANCHOR)
    with TestClient(app) as c:
        yield c


def company(c, ticker):
    return next(x for x in c.get("/api/admin/companies").json() if x["ticker"] == ticker)


def body(co, **changes):
    keys = ["ticker", "name", "exchange", "sector", "is_demo", "market_cap_usd_m", "analyst_count", "benchmark_ticker",
            "next_earnings_date", "earnings_date_confirmed", "fiscal_quarter_end", "cashtag_exclusions", "active", "notes"]
    return {**{k: co[k] for k in keys}, **changes}


def test_past_earnings_company_is_flagged_first(client):
    first = client.get("/api/admin/companies").json()[0]
    assert first["ticker"] == "FIVE" and first["earnings"]["needs_date_update"]
    assert "past" in first["earnings"]["reason"]


def test_manual_earnings_fix_wins_over_feed_and_survives_ingest(client):
    five = company(client, "FIVE")
    new_date = (ANCHOR + timedelta(days=50)).isoformat()
    r = client.put(f"/api/admin/companies/{five['id']}", json=body(five, next_earnings_date=new_date,
                                                                    fiscal_quarter_end=(ANCHOR + timedelta(days=5)).isoformat()))
    assert r.status_code == 200
    assert r.json()["earnings"]["status"] == "inside_window" and r.json()["earnings"]["source"] == "manual"
    assert client.post("/api/ingest", json={"as_of": ANCHOR.isoformat()}).json()["ok"]
    assert company(client, "FIVE")["earnings"]["source"] == "manual"          # the stale feed does not undo it
    scan = client.post("/api/scan", json={"as_of": ANCHOR.isoformat()}).json()
    assert scan["ok"]
    rows = client.get("/api/watchlist", params={"earnings_window": False}).json()["rows"]
    assert all(r["earnings_status"] != "unknown" for r in rows if r["ticker"] == "FIVE")


def test_company_and_product_validation(client):
    assert client.post("/api/admin/companies", json={"ticker": "crox", "name": "Dup"}).status_code == 409
    crox = company(client, "CROX")
    assert client.put(f"/api/admin/companies/{crox['id']}", json=body(crox, ticker="CRX")).status_code == 422
    new = client.post("/api/admin/companies", json={"ticker": "newco", "name": "New Co", "benchmark_ticker": "xrt"})
    assert new.status_code == 200 and new.json()["ticker"] == "NEWCO" and new.json()["benchmark_ticker"] == "XRT"
    p = client.post("/api/admin/products", json={"company_id": crox["id"], "name": "Echo slide"})
    assert p.status_code == 409
    bad = client.post("/api/admin/products", json={"company_id": 9999, "name": "x"})
    assert bad.status_code == 404


def test_add_product_then_daily_updates_alert_log(client):
    before = client.get("/api/alerts").json()["total"]
    crox = company(client, "CROX")
    p = client.post("/api/admin/products", json={"company_id": crox["id"], "name": "Mega crush clog",
                                                 "keywords": ["crocs mega crush"]}).json()
    daily = client.post("/api/daily", json={"as_of": ANCHOR.isoformat()}).json()
    assert daily["ok"], daily
    # the new product was backfilled with full history, not just the incremental window
    with session_factory()() as s:
        n = s.scalar(select(func.count()).select_from(Observation).where(
            Observation.source == "social_mentions", Observation.entity_key == str(p["id"]),
            Observation.metric == "mentions"))
        assert n > 300
    log = client.get("/api/alerts").json()
    assert log["total"] == before + 1
    assert log["items"][0]["product"] == "Mega crush clog" and log["items"][0]["stage"] == "entry_review"


def test_announcements_crud(client):
    crox = company(client, "CROX")
    a = client.post("/api/admin/announcements", json={"company_id": crox["id"], "event_date": ANCHOR.isoformat(),
                                                      "type": "partnership", "title": "New collab"}).json()
    assert a["ticker"] == "CROX"
    upd = client.put(f"/api/admin/announcements/{a['id']}", json={**{k: a[k] for k in (
        "company_id", "product_id", "event_date", "type", "url", "notes")}, "title": "Renamed collab"})
    assert upd.json()["title"] == "Renamed collab"
    other = company(client, "ONON")
    wrong = client.post("/api/admin/announcements", json={"company_id": other["id"], "product_id": 1,
                                                          "event_date": ANCHOR.isoformat(), "type": "other",
                                                          "title": "x"})
    assert wrong.status_code == 422                           # product 1 belongs to CROX
    assert client.delete(f"/api/admin/announcements/{a['id']}").json()["ok"]
    assert all(x["id"] != a["id"] for x in client.get("/api/admin/announcements").json())


def test_csv_import_is_all_or_nothing(client):
    companies_csv = ("ticker,name,sector,benchmark_ticker,next_earnings_date,earnings_date_confirmed\n"
                     "NEWA,New A Inc,apparel,XLY,2026-12-01,yes\nCROX,Crocs Renamed,apparel,XLY,,\n")
    dry = client.post("/api/admin/import/companies", json={"csv": companies_csv, "dry_run": True}).json()
    assert dry == {"created": 1, "updated": 1, "errors": [], "applied": False}
    assert all(c["ticker"] != "NEWA" for c in client.get("/api/admin/companies").json())
    done = client.post("/api/admin/import/companies", json={"csv": companies_csv}).json()
    assert done["applied"] and company(client, "CROX")["name"] == "Crocs Renamed"

    bad = client.post("/api/admin/import/products", json={
        "csv": "ticker,name,keywords\nNEWA,Thing,thing one;thing two\nNOPE,X,x\nNEWA,,y\n"}).json()
    assert not bad["applied"] and [e["line"] for e in bad["errors"]] == [3, 4]
    assert all(p["ticker"] != "NEWA" for p in client.get("/api/admin/products").json())
    ok = client.post("/api/admin/import/products", json={"csv": "ticker,name,keywords\nNEWA,Thing,thing one;thing two\n"}).json()
    assert ok["created"] == 1
    p = next(p for p in client.get("/api/admin/products").json() if p["ticker"] == "NEWA")
    assert p["keywords"] == ["thing one", "thing two"]
    assert client.post("/api/admin/import/products", json={"csv": "ticker\nCROX\n"}).status_code == 422
