"""Operator views: the dashboard read model and the ticker page."""
from fastapi.testclient import TestClient

from app.main import app
from app.pipeline.narrative import short_name


def test_short_names():
    assert short_name("Crocs, Inc.") == "Crocs"
    assert short_name("On Holding AG") == "On Holding"
    assert short_name("YETI Holdings, Inc.") == "YETI"
    assert short_name("Demo Outfitters Co. (fictional)") == "Demo Outfitters"


def test_dashboard_is_one_row_per_ticker_with_buy_and_sell_sides(seeded_db):
    with TestClient(app) as c:
        d = c.get("/api/dashboard").json()
    board = d["board"]
    assert len(board) == len({r["ticker"] for r in board}) == 12
    assert {r["ticker"] for r in d["buy"]} == {"CROX", "WRBY", "COTY", "ELF"}
    assert [r["ticker"] for r in d["sell"]] == ["ONON"]
    assert {r["label"] for r in d["buy"]} == {"Entry signal", "Early mover"}
    assert d["kpis"]["entry"]["count"] == 3 and d["kpis"]["exit"]["count"] == 1
    text = "".join(s["text"] for s in d["headline"])
    assert "Warby Parker" in text and "Coty" in text and "Crocs" in text and "On Holding" in text
    radar = {r["ticker"]: r["kind"] for r in d["radar"]}
    assert radar == {"OLPX": "watch", "BIRK": "gap", "BOOT": "chatter", "FIVE": "earnings"}
    crox = next(r for r in board if r["ticker"] == "CROX")
    assert crox["product"] == "Charm clog collab"            # strongest product represents the ticker
    assert len(crox["buzz_spark"]) == 45 and len(crox["price_spark"]) > 20
    assert crox["buzz_spark"][-1] > 180                      # buzz has more than doubled over the window
    assert {r["ticker"] for r in board if r["label"] == "Seasonal"} == {"YETI"}
    assert not d["health"]["ok"] and {i["source"] for i in d["health"]["issues"]} == {"price", "social_mentions"}


def test_ticker_page_explains_the_signal(seeded_db):
    with TestClient(app) as c:
        t = c.get("/api/tickers/crox").json()
        assert t["product"]["name"] == "Charm clog collab"
        assert t["signal"]["label"] == "Entry signal"
        assert "2.2× normal" in t["signal"]["verdict"] and "70 days out" in t["signal"]["verdict"]
        assert all(ch["ok"] for ch in t["signal"]["checks"])
        assert t["decision"]["alert_id"] is not None
        assert t["chart"]["buzz"] and t["chart"]["price_rel"]
        assert t["earnings"]["status"] == "inside_window" and t["earnings"]["window"] == [42, 98]
        assert [p["stage"] for p in t["products"]][0] == "entry_review"

        birk = c.get("/api/tickers/BIRK").json()
        assert birk["signal"]["label"] == "Data gap" and "6 days old" in birk["signal"]["verdict"]
        assert birk["decision"]["alert_id"] is None
        onon = c.get("/api/tickers/ONON").json()
        assert onon["signal"]["side"] == "sell" and "crowded" in onon["signal"]["verdict"]
        five = c.get("/api/tickers/FIVE").json()
        assert "needs an update" in five["signal"]["verdict"]
        other = c.get("/api/tickers/CROX", params={"product_id": t["products"][-1]["id"]}).json()
        assert other["product"]["id"] == t["products"][-1]["id"]
        assert c.get("/api/tickers/NOPE").status_code == 404
