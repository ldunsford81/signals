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
