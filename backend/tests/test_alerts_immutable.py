"""Alerts are never updated by a second scan or by a config change."""
from sqlalchemy import select

from app.core.config import load_settings
from app.db.models import Alert, ConfigVersion, Scan
from app.db.session import session_factory
from app.pipeline.scan import run_scan
from app.pipeline.seed import seed
from conftest import ANCHOR


def snapshot_alerts(s):
    return {a.id: (a.stage, a.summary, a.config_hash, a.changed_fields, a.input_snapshot, a.created_at)
            for a in s.scalars(select(Alert))}


def test_alerts_survive_rescans_and_config_changes(tmp_env, settings):
    seed(settings)
    with session_factory()() as s:
        first = run_scan(s, settings, as_of=ANCHOR)
        before = snapshot_alerts(s)
        assert first.alerts_created == len(before) > 0

        # Same date, same config: no duplicates, nothing rewritten.
        again = run_scan(s, settings, as_of=ANCHOR)
        assert again.alerts_created == 0
        assert snapshot_alerts(s) == before

        # Change a threshold: new alerts carry the new config hash; old ones are untouched.
        changed = load_settings(overrides={"demo": {"anchor_date": ANCHOR.isoformat()},
                                           "price_response": {"early_move": {"min_relative_return": 0.035,
                                                                             "min_volume_ratio": 1.5}}})
        assert changed.hash() != settings.hash()
        third = run_scan(s, changed, as_of=ANCHOR)
        after = snapshot_alerts(s)
        for aid, row in before.items():
            assert after[aid] == row
        new = [row for aid, row in after.items() if aid not in before]
        assert third.alerts_created == len(new) > 0
        assert {row[2] for row in new} == {changed.hash()}
        assert {c.config_hash for c in s.scalars(select(ConfigVersion))} == {settings.hash(), changed.hash()}
        assert s.scalar(select(Scan).where(Scan.id == third.scan_id)).config_hash == changed.hash()


def test_next_day_only_alerts_on_transitions(tmp_env, settings):
    from app.core import calendar
    from app.pipeline.ingest import run_ingest
    seed(settings)
    nxt = calendar.add_sessions(ANCHOR, 1)
    with session_factory()() as s:
        run_scan(s, settings, as_of=ANCHOR)
        run_ingest(s, settings, as_of=nxt)
        r = run_scan(s, settings, as_of=nxt)
        new = s.scalars(select(Alert).where(Alert.scan_id == r.scan_id)).all()
        for a in new:
            assert a.prior_stage != a.stage or any(c["field"] in ("price_response", "retail_status")
                                                   for c in a.changed_fields)
