"""Review feed: grouping, reasons, health panel, decisions, and stay-in-stage behaviour."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import calendar
from app.db.models import Alert, AlertReview
from app.db.session import session_factory
from app.main import app
from app.pipeline.feed import build_feed
from app.pipeline.ingest import run_ingest
from app.pipeline.scan import run_scan
from app.pipeline.seed import seed
from conftest import ANCHOR


def test_feed_shows_reportable_cases_with_reasons(seeded_db):
    with TestClient(app) as c:
        f = c.get("/api/feed").json()
    cards = [card for g in f["groups"] for card in g["cards"]]
    assert {(card["ticker"], card["stage"]) for card in cards} == {
        ("ONON", "exit_review"), ("CROX", "entry_review"), ("WRBY", "entry_review"),
        ("COTY", "entry_review"), ("ELF", "early_recognition")}
    assert cards[0]["stage"] == "exit_review"                      # ordered as the watchlist
    assert f["counts"] == {"exit_review": 1, "entry_review": 3, "early_recognition": 1}
    for card in cards:
        assert card["reason"] and card["summary"].startswith(card["product"])
        assert card["alert_id"] is not None
    entry = next(card for card in cards if card["ticker"] == "CROX")
    assert "earnings 42–98 days out" in entry["reason"]
    # data_gap goes to the health panel, not the cards
    assert [h["ticker"] for h in f["health"]] == ["BIRK"]
    assert f["health"][0]["unknown_inputs"][0]["family"] == "price"
    assert "stale" in f["health"][0]["unknown_inputs"][0]["reason"]


def test_decisions_are_logged_and_never_touch_alerts(seeded_db):
    with TestClient(app) as c:
        card = next(cd for g in c.get("/api/feed").json()["groups"] for cd in g["cards"] if cd["ticker"] == "ELF")
        aid = card["alert_id"]
        with session_factory()() as s:
            before = {a.id: (a.stage, a.summary, a.input_snapshot) for a in s.scalars(select(Alert))}

        assert c.post(f"/api/alerts/{aid}/review", json={"decision": "acted", "note": " starter "}).status_code == 200
        assert c.post(f"/api/alerts/{aid}/review", json={"decision": "passed"}).status_code == 200
        card = next(cd for g in c.get("/api/feed").json()["groups"] for cd in g["cards"] if cd["ticker"] == "ELF")
        assert card["decision"] == "passed" and card["note"] is None   # latest row wins
        history = c.get(f"/api/alerts/{aid}/reviews").json()
        assert [h["decision"] for h in history] == ["passed", "acted"]
        assert history[1]["note"] == "starter"

        assert c.post(f"/api/alerts/{aid}/review", json={"decision": "sold"}).status_code == 422
        assert c.post("/api/alerts/99999/review", json={"decision": "acted"}).status_code == 404
        with session_factory()() as s:
            after = {a.id: (a.stage, a.summary, a.input_snapshot) for a in s.scalars(select(Alert))}
            assert after == before
            assert s.query(AlertReview).filter(AlertReview.alert_id == aid).count() == 2


def test_products_staying_in_stage_remain_in_feed_without_new_alerts(tmp_env, settings):
    seed(settings)
    nxt = calendar.add_sessions(ANCHOR, 1)
    with session_factory()() as s:
        run_scan(s, settings, as_of=ANCHOR)
        first = {cd["product_id"]: cd for g in build_feed(s, settings)["groups"] for cd in g["cards"]}
        run_ingest(s, settings, as_of=nxt)
        r = run_scan(s, settings, as_of=nxt)
        feed = build_feed(s, settings)
        assert feed["prior_as_of"] == ANCHOR
        cards = {cd["product_id"]: cd for g in feed["groups"] for cd in g["cards"]}
        new_alerts = {a.product_id for a in s.scalars(select(Alert).where(Alert.scan_id == r.scan_id))}
        stayed = [pid for pid, cd in cards.items() if pid in first and cd["stage"] == first[pid]["stage"]]
        assert stayed, "expected at least one product to stay in its stage"
        for pid in stayed:
            cd = cards[pid]
            assert not cd["is_new"]
            if not any(ch["field"] in ("price", "retail") for ch in cd["changes"]):
                assert pid not in new_alerts                   # no change → no new alert, still in the feed
                assert cd["alert_id"] == first[pid]["alert_id"]
