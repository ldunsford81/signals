"""Replay, evaluate and the rules-performance summary."""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core import calendar
from app.core.config import load_settings
from app.db.models import Alert, AlertOutcome, Observation, Scan
from app.db.session import get_engine, session_factory
from app.main import app
from app.pipeline.evaluate import counted_ids, hit_rule, run_evaluate
from app.pipeline.replay import run_replay
from app.pipeline.scan import run_scan
from app.pipeline.seed import seed
from conftest import ANCHOR


@pytest.fixture(scope="module")
def replayed(tmp_path_factory):
    """Fresh install: seed, full replay over the seeded history, evaluate (about a minute)."""
    root = tmp_path_factory.mktemp("replayed")
    mp = pytest.MonkeyPatch()
    mp.setenv("CTM_DATA_DIR", str(root / "data"))
    mp.setenv("CTM_BACKUP_DIR", str(root / "backups"))
    get_engine.cache_clear()
    s = load_settings(overrides={"demo": {"anchor_date": ANCHOR.isoformat()}})
    seed(s)
    with session_factory()() as ses:
        rep = run_replay(ses, s)
        ev = run_evaluate(ses, s)
    yield {"settings": s, "replay": rep, "evaluate": ev}
    get_engine.cache_clear()
    mp.undo()


def test_replay_covers_history_and_tags_alerts(replayed):
    rep = replayed["replay"]
    assert rep["scans_run"] > 200 and rep["end"] == ANCHOR
    with session_factory()() as s:
        triggers = {t for (t,) in s.execute(select(Scan.trigger).join(Alert, Alert.scan_id == Scan.id))}
        assert triggers == {"replay"}
        first_obs = s.scalar(select(func.min(Observation.obs_date)))
        assert rep["start"] >= first_obs + timedelta(days=60)
        # replay reads a later search snapshot truncated to as_of, and says so
        a = s.scalars(select(Alert)).first()
        assert a.input_snapshot["input_health"]["flags"]["rescaled_history"] is True


def test_replay_is_idempotent(replayed):
    with session_factory()() as s:
        before = s.scalar(select(func.count()).select_from(Alert))
        again = run_replay(s, replayed["settings"])
        assert again["scans_run"] == 0 and again["alerts_created"] == 0
        assert s.scalar(select(func.count()).select_from(Alert)) == before


def test_evaluate_returns_match_prices(replayed):
    with session_factory()() as s:
        o = s.scalars(select(AlertOutcome).where(AlertOutcome.horizon == "5d", AlertOutcome.complete.is_(True))).first()
        a = s.get(Alert, o.alert_id)
        end = calendar.add_sessions(a.as_of, 5)

        def close(ticker, d):
            return s.scalar(select(Observation.value).where(
                Observation.source == "price", Observation.entity_key == ticker, Observation.metric == "close",
                Observation.obs_date <= d).order_by(Observation.obs_date.desc()).limit(1))
        t, b = a.input_snapshot["company"]["ticker"], a.input_snapshot["company"]["benchmark"]
        stock = close(t, end) / close(t, a.as_of) - 1
        bench = close(b, end) / close(b, a.as_of) - 1
        assert o.stock_return == pytest.approx(stock)
        assert o.excess_return == pytest.approx(stock - bench)
        # horizons that run past the last stored price are not complete
        late = s.scalars(select(Alert).where(Alert.as_of >= ANCHOR - timedelta(days=10))).first()
        if late:
            outs = {x.horizon: x for x in s.scalars(select(AlertOutcome).where(AlertOutcome.alert_id == late.id))}
            assert outs["60d"].complete is False


def test_performance_table_is_filled_with_a_mixed_record(replayed):
    with TestClient(app) as c:
        p = c.get("/api/evaluation").json()
    groups = {g["stage"]: g for g in p["groups"] if g["trigger"] == "replay"}
    assert set(groups) == {"entry_review", "early_recognition", "exit_review"}
    rates = [h["hit_rate"] for g in groups.values() for h in g["horizons"].values() if h["n"] > 0]
    assert any(0 < r < 1 for r in rates)                       # mixed, not all wins or all losses
    assert any(h["judged"] for g in groups.values() for h in g["horizons"].values())
    assert any(not h["judged"] for g in groups.values() for h in g["horizons"].values())
    assert groups["exit_review"]["headline_horizon"] == "20d"
    assert groups["exit_review"]["n_counted"] < groups["exit_review"]["n_alerts"]   # dedupe applied


def test_live_scan_after_replay_does_not_diff_against_replay(replayed):
    with session_factory()() as s:
        r = run_scan(s, replayed["settings"], as_of=ANCHOR, trigger="manual")
        live = s.scalars(select(Alert).where(Alert.scan_id == r.scan_id)).all()
        assert live and all(a.prior_stage is None for a in live)   # first live scan: no prior in its lineage
    with TestClient(app) as c:
        groups = c.get("/api/evaluation").json()["groups"]
        assert {g["trigger"] for g in groups} == {"live", "replay"}
        combined = c.get("/api/evaluation", params={"combine_triggers": True}).json()["groups"]
        assert {g["trigger"] for g in combined} == {"all"}
        log = c.get("/api/alerts", params={"trigger": "live"}).json()
        assert log["total"] == len(live)
        d = c.get(f"/api/alerts/{log['items'][0]['id']}").json()
        assert d["input_snapshot"]["stage"] == d["stage"]


# ---- pure logic ----------------------------------------------------------------
def _row(aid, company, stage, as_of, trigger="replay", cfg="c1"):
    return (SimpleNamespace(id=aid, company_id=company, stage=stage, as_of=as_of, config_hash=cfg),
            SimpleNamespace(trigger=trigger))


def test_dedupe_counts_first_alert_per_company_stage_window():
    d0 = date(2026, 1, 1)
    rows = [_row(1, 1, "entry_review", d0), _row(2, 1, "entry_review", d0 + timedelta(days=10)),
            _row(3, 1, "entry_review", d0 + timedelta(days=31)), _row(4, 2, "entry_review", d0 + timedelta(days=5)),
            _row(5, 1, "exit_review", d0 + timedelta(days=10)), _row(6, 1, "entry_review", d0, trigger="manual")]
    assert counted_ids(rows, 30) == {1, 3, 4, 5, 6}
    assert counted_ids(rows, 30, combine=True) == {1, 3, 4, 5}


def test_hit_rules():
    s = load_settings()
    assert hit_rule(s, "entry_review")[:2] == (1, None)
    assert hit_rule(s, "exit_review")[:2] == (-1, "20d")
