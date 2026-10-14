"""Seed, scan, and check that the 12 required scenarios produce their expected results."""
import pytest
from sqlalchemy import select

from app.db.models import Alert, Company, Product, SignalState
from app.db.session import session_factory
from app.sources.demo.universe import EXPECTED


def states(scan_id):
    with session_factory()() as s:
        rows = s.execute(select(SignalState, Product, Company).join(Product, Product.id == SignalState.product_id)
                         .join(Company, Company.id == Product.company_id).where(SignalState.scan_id == scan_id)).all()
        return {(c.ticker, p.name): st for st, p, c in rows}


@pytest.mark.parametrize("key", list(EXPECTED))
def test_scenario(seeded_db, key):
    st = states(seeded_db["scan"].scan_id)[key]
    exp = EXPECTED[key]
    assert st.stage == exp["stage"], (key, st.stage, st.attention_status, st.price_response, st.retail_status)
    if "attention" in exp:
        assert st.attention_status == exp["attention"]
    if "retail" in exp:
        assert st.retail_status == exp["retail"]
    if "price" in exp:
        assert st.price_response == exp["price"]
    if exp.get("single_source"):
        assert st.input_health["flags"]["single_source"] is True
    if exp.get("quarter_closed"):
        assert st.days_left_in_quarter <= 0 and st.input_health["flags"]["quarter_closed"]
    if exp.get("earnings_unknown"):
        assert st.input_health["earnings"]["status"] == "unknown"
        assert "past" in st.input_health["earnings"]["reason"]


def test_scenario_details(seeded_db):
    st = states(seeded_db["scan"].scan_id)
    crox = st[("CROX", "Charm clog collab")]
    assert crox.days_to_earnings == 70 and crox.days_left_in_quarter > 0
    assert crox.price_response == "flat" and crox.retail_status == "quiet"
    assert st[("OLPX", "No.4 bond shampoo")].days_to_earnings == 150
    boot = st[("BOOT", "Western work boot")]
    assert boot.retail_components["sources"]["cashtag_mentions"]["ratio"] >= 3.0       # 4x burst ...
    assert boot.retail_components["sources"]["cashtag_mentions"]["breadth"]["result"] == "too_few_accounts"
    birk = st[("BIRK", "Boston clog suede")]
    assert "stale" in birk.price_components["reason"]
    # Remaining names are flat: no other product has a stage.
    named = set(EXPECTED)
    others = {k: v.stage for k, v in st.items() if k not in named}
    assert set(others.values()) == {"none"}, others


def test_alerts_for_reportable_scenarios_only(seeded_db):
    with session_factory()() as s:
        alerts = s.execute(select(Alert, Product).join(Product, Product.id == Alert.product_id)).all()
    got = sorted((p.name, a.stage) for a, p in alerts)
    assert got == sorted([
        ("Charm clog collab", "entry_review"), ("Cloudtilt trainer", "exit_review"),
        ("Glow reviver lip oil", "early_recognition"), ("Contact lens subscription", "entry_review"),
        ("Burberry Goddess fragrance", "entry_review")])
    for a, _ in alerts:
        assert a.summary and "days to earnings" in a.summary
        assert a.input_snapshot["stage"] == a.stage and a.config_hash == seeded_db["scan"].config_hash
