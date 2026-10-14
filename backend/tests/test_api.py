from fastapi.testclient import TestClient

from app.main import app


def test_watchlist_defaults_to_earnings_window(seeded_db):
    with TestClient(app) as c:
        w = c.get("/api/watchlist").json()
        assert w["scan"]["as_of"] == "2026-10-13"
        lo, hi = w["earnings_window_days"]
        assert all(lo <= r["days_to_earnings"] <= hi for r in w["rows"])
        tickers = {r["ticker"] for r in w["rows"]}
        assert "OLPX" not in tickers                         # 150 days out: hidden by default
        assert w["rows"][0]["stage"] == "entry_review"       # exit (ONON, 30d) is outside the window
        everything = c.get("/api/watchlist", params={"earnings_window": False}).json()
        assert len(everything["rows"]) == everything["total"] == 26
        stages = [r["stage"] for r in everything["rows"]]
        assert stages[0] == "exit_review"
        watch = c.get("/api/watchlist", params={"earnings_window": False, "stage": "watch"}).json()
        assert [r["ticker"] for r in watch["rows"]] == ["OLPX"]


def test_status_reports_partial_sources(seeded_db):
    with TestClient(app) as c:
        st = c.get("/api/status").json()
        assert st["demo_mode"] is True
        assert any("BIRK" in w for w in st["warnings"])


def test_scan_endpoint_reports_config_errors(seeded_db, tmp_path, monkeypatch):
    bad = tmp_path / "bad.yaml"
    bad.write_text("stages: nope\n")
    monkeypatch.setenv("CTM_CONFIG", str(bad))
    with TestClient(app) as c:
        r = c.post("/api/scan", json={}).json()
    assert r["ok"] is False and "Invalid config" in r["error"]


def _product_id(c, ticker, name):
    rows = c.get("/api/watchlist", params={"earnings_window": False}).json()["rows"]
    return next(r["product_id"] for r in rows if r["ticker"] == ticker and r["product"] == name)


def test_product_detail_series_and_markers(seeded_db):
    with TestClient(app) as c:
        pid = _product_id(c, "ONON", "Cloudtilt trainer")
        d = c.get(f"/api/products/{pid}", params={"days": 90}).json()
        assert d["state"]["stage"] == "exit_review"
        assert d["state"]["signal_start_date"] is not None
        # one panel per configured source, each covering the window
        assert [s["source"] for s in d["attention_series"]] == ["search_interest", "social_mentions"]
        assert [s["source"] for s in d["retail_series"]] == ["ticker_search_interest", "cashtag_mentions"]
        assert len(d["attention_series"][0]["points"]) == 90
        last = d["attention_series"][0]["points"][-1]
        assert last["band_low"] < last["baseline_mean"] < last["band_high"]
        # benchmark is rebased to the stock's close on the anchor base date
        base = d["state"]["price_components"]["base_date"]
        assert d["benchmark_rebased_on"] == base
        on_base = next(p for p in d["price_series"] if p["date"] == base)
        assert abs(on_base["benchmark_rebased"] - on_base["close"]) < 0.01
        assert {a["title"] for a in d["announcements"]} >= {"Expanded wholesale distribution in Asia"}
        assert d["history"][0]["stage"] == "exit_review"
        assert d["alerts"][0]["stage"] == "exit_review"


def test_product_detail_with_unknown_price_and_missing_product(seeded_db):
    with TestClient(app) as c:
        pid = _product_id(c, "BIRK", "Boston clog suede")
        d = c.get(f"/api/products/{pid}").json()
        assert d["state"]["price_response"] == "unknown"
        assert d["benchmark_rebased_on"] is not None          # falls back to the window start
        assert d["price_series"][-1]["date"] < d["scan"]["as_of"]   # stale feed: no bars at the end
        assert c.get("/api/products/99999").status_code == 404
