from datetime import date, datetime, timezone

import pytest

from app.core import calendar
from app.core.config import ConfigError, load_settings


def test_config_loads_and_hash_is_stable():
    a, b = load_settings(), load_settings()
    assert a.hash() == b.hash()
    assert [r.name for r in a.stages] == ["data_gap", "exit_review", "entry_review", "early_recognition", "watch"]


def test_threshold_change_changes_hash():
    a = load_settings()
    b = load_settings(overrides={"attention": {"accelerating": {"min_ratio": 1.6, "min_z": 2.0}}})
    assert a.hash() != b.hash()


@pytest.mark.parametrize("override, fragment", [
    ({"stages": [{"name": "x", "when": {"price": ["sideways"]}}]}, "price values"),
    ({"attention": {"accelerating": {"min_ratio": "lots", "min_z": 2}}}, "attention.accelerating.min_ratio"),
    ({"families": {"attention": [{"source": "nope", "metric": "m"}],
                   "price": {"close": {"source": "price", "metric": "close"},
                             "volume": {"source": "price", "metric": "volume"}}, "retail": []}}, "unknown source"),
    ({"sources": {"price": {"mode": "sometimes"}}}, "sources.price.mode"),
])
def test_invalid_config_raises_readable_error(override, fragment):
    with pytest.raises(ConfigError) as e:
        load_settings(overrides=override)
    assert fragment in str(e.value)


def test_trading_calendar():
    assert calendar.is_session(date(2026, 10, 13))
    assert not calendar.is_session(date(2026, 10, 10))                 # Saturday
    assert not calendar.is_session(date(2026, 11, 26))                 # Thanksgiving
    assert calendar.session_on_or_before(date(2026, 10, 11)) == date(2026, 10, 9)
    # 05:35 UTC Wednesday = Tuesday's session is the last completed one
    assert calendar.last_completed_session(datetime(2026, 10, 14, 5, 35, tzinfo=timezone.utc)) == date(2026, 10, 13)
    # 15:00 UTC Wednesday = still trading, so Tuesday
    assert calendar.last_completed_session(datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)) == date(2026, 10, 13)
    assert calendar.last_completed_session(datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc)) == date(2026, 10, 14)
    assert calendar.add_sessions(date(2026, 10, 13), 5) == date(2026, 10, 20)


def test_cron_weekdays_follow_standard_cron():
    from zoneinfo import ZoneInfo

    from app.main import cron_trigger
    t = cron_trigger("30 8 * * 2-6", "Australia/Sydney")
    d = datetime(2026, 10, 12, 9, 0, tzinfo=ZoneInfo("Australia/Sydney"))   # Monday
    days = []
    for _ in range(5):
        d = t.get_next_fire_time(None, d)
        days.append(d.strftime("%a"))
        d = d.replace(minute=31)
    assert days == ["Tue", "Wed", "Thu", "Fri", "Sat"]
