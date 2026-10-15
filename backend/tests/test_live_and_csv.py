"""Step 12: live stubs skip cleanly, earnings CSV mode, backup."""
import socket
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import load_settings
from app.db.models import Company
from app.db.session import session_factory
from app.main import app
from app.pipeline import jobs
from app.pipeline.ingest import run_ingest
from app.pipeline.scan import run_scan
from app.pipeline.seed import seed
from app.sources import registry
from conftest import ANCHOR

KEYS = ["TRENDS_PROVIDER_API_KEY", "YOUTUBE_API_KEY", "PRICE_VENDOR_API_KEY", "EARNINGS_CALENDAR_API_KEY", "X_BEARER_TOKEN"]


def with_modes(**modes):
    return load_settings(overrides={"demo": {"anchor_date": ANCHOR.isoformat()},
                                    "sources": {k: v if isinstance(v, dict) else {"mode": v} for k, v in modes.items()}})


def test_every_source_has_a_live_adapter():
    for name, modes in registry.REGISTRY.items():
        assert "demo" in modes and "live" in modes, name


def test_live_without_credentials_is_skipped_and_the_rest_keeps_working(tmp_env, settings, monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    seed(settings)
    live = with_modes(cashtag_mentions="live", social_mentions="live")
    with session_factory()() as s:
        runs = {r.source: r for r in run_ingest(s, live, as_of=ANCHOR)}
        assert runs["cashtag_mentions"].status == "skipped" and "X_BEARER_TOKEN" in runs["cashtag_mentions"].message
        assert runs["social_mentions"].status == "skipped" and "YOUTUBE_API_KEY" in runs["social_mentions"].message
        assert runs["price"].status in ("ok", "partial") and runs["search_interest"].status == "ok"
        run_scan(s, live, as_of=ANCHOR)                     # scan still works on the stored data
    with TestClient(app) as c:
        st = {x["source"]: x for x in c.get("/api/status").json()["sources"]}
        assert st["cashtag_mentions"]["last_run_status"] == "skipped"
        assert "X_BEARER_TOKEN" in st["cashtag_mentions"]["error_message"]
        assert c.get("/api/dashboard").status_code == 200


def test_live_stub_with_credentials_still_skips_without_network(tmp_env, settings, monkeypatch):
    for k in KEYS:
        monkeypatch.setenv(k, "test-key")
    calls = []
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: calls.append(a))
    seed(settings)
    live = with_modes(**{n: "live" for n in registry.REGISTRY})
    with session_factory()() as s:
        runs = run_ingest(s, live, as_of=ANCHOR)
    assert {r.status for r in runs} == {"skipped"}
    assert all("not built yet" in r.message for r in runs)
    assert calls == []


def test_earnings_csv_mode(tmp_env, settings, tmp_path):
    seed(settings)
    good = tmp_path / "earnings.csv"
    good.write_text("ticker,next_earnings_date,confirmed,fiscal_quarter_end,as_of\n"
                    f"FIVE,2026-12-03,yes,2026-10-19,{ANCHOR}\n"
                    f"CROX,2026-12-23,no,2026-11-08,{ANCHOR}\n"
                    "CROX,not-a-date,no,,\n")
    csv_cfg = with_modes(earnings={"mode": "csv", "csv": str(good)})
    with session_factory()() as s:
        run = {r.source: r for r in run_ingest(s, csv_cfg, as_of=ANCHOR, only=["earnings"])}["earnings"]
        assert run.status == "partial"                       # rows for other tickers are missing, one row is bad
        assert "line 4" in run.message and "no earnings row" in run.message
        five = s.scalar(select(Company).where(Company.ticker == "FIVE"))
        assert str(five.next_earnings_date) == "2026-12-03" and five.earnings_date_confirmed
        r = run_scan(s, csv_cfg, as_of=ANCHOR)
    with TestClient(app) as c:
        rows = c.get("/api/watchlist", params={"earnings_window": False}).json()["rows"]
        assert all(x["earnings_status"] == "inside_window" for x in rows if x["ticker"] == "FIVE")

    missing = with_modes(earnings={"mode": "csv", "csv": str(tmp_path / "nope.csv")})
    with session_factory()() as s:
        run = run_ingest(s, missing, as_of=ANCHOR, only=["earnings"])[0]
    assert run.status == "error" and "nope.csv" in run.message


def test_checked_in_earnings_csv_covers_the_demo_universe():
    from app.sources.demo.universe import COMPANIES
    text = (Path(__file__).resolve().parents[2] / "data" / "earnings.csv").read_text()
    tickers = {line.split(",")[0] for line in text.strip().splitlines()[1:]}
    assert tickers == {c.ticker for c in COMPANIES}


def test_backup_copies_the_database(tmp_env, settings):
    seed(settings)
    out = jobs.backup_job()
    p = Path(out["backup"])
    assert p.exists() and p.name.startswith("socialarb-") and p.stat().st_size > 100_000
