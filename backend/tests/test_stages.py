from datetime import date, timedelta

import pytest

from app.core.config import load_settings
from app.stages.engine import StageInputs, evaluate
from helpers import AS_OF


def x(attention="elevated", price="flat", retail="quiet", earnings="inside_window", elevated_days_ago=0,
      quarter_open=True):
    last = AS_OF - timedelta(days=elevated_days_ago) if elevated_days_ago is not None else None
    return StageInputs(AS_OF, attention, price, retail, earnings, last, quarter_open)


@pytest.mark.parametrize("inputs, expected", [
    (x(), "entry_review"),
    (x(price="early_move"), "early_recognition"),
    (x(price="early_move", retail="rising"), "exit_review"),          # exit is checked before early recognition
    (x(price="clear_acceleration", retail="elevated"), "exit_review"),
    (x(price="clear_acceleration"), "watch"),
    (x(earnings="outside_window"), "watch"),
    (x(attention="normal"), "none"),
    (x(attention="seasonal", elevated_days_ago=None), "none"),
])
def test_default_rules(settings, inputs, expected):
    assert evaluate(inputs, settings)[0] == expected


def test_data_gap_is_checked_first(settings):
    assert evaluate(x(price="unknown"), settings)[0] == "data_gap"
    assert evaluate(x(retail="unknown", price="early_move"), settings)[0] == "data_gap"
    assert evaluate(x(earnings="unknown"), settings)[0] == "data_gap"
    # attention elevated 8 days ago (not now) still counts for data_gap
    assert evaluate(x(attention="normal", elevated_days_ago=8, price="unknown"), settings)[0] == "data_gap"
    # ... but not 15 days ago
    assert evaluate(x(attention="normal", elevated_days_ago=15, price="unknown"), settings)[0] == "none"


def test_exit_before_entry_and_needs_recent_attention(settings):
    # Retail chatter on a name otherwise in entry shape is never shown as an entry.
    assert evaluate(x(retail="rising", price="early_move"), settings)[0] == "exit_review"
    # Momentum with attention elevated 45 days ago still counts; 70 days ago does not.
    assert evaluate(x(attention="normal", elevated_days_ago=45, price="early_move", retail="rising"), settings)[0] == "exit_review"
    assert evaluate(x(attention="normal", elevated_days_ago=70, price="early_move", retail="rising"), settings)[0] == "none"


def test_entry_never_fires_with_unknown_input(settings):
    # Even with a custom rule list that drops data_gap, entry refuses unknown inputs.
    s = load_settings(overrides={"stages": [
        {"name": "entry_review", "when": {"attention": ["elevated"]}},
        {"name": "watch", "when": {"attention": ["elevated"]}}],
        "reportable_stages": ["entry_review"]})
    assert evaluate(x(), s)[0] == "entry_review"
    assert evaluate(x(price="unknown"), s)[0] == "watch"
    assert evaluate(x(earnings="unknown"), s)[0] == "watch"


def test_rule_order_comes_from_config():
    s = load_settings(overrides={"stages": [
        {"name": "watch", "when": {"attention": ["elevated"]}},
        {"name": "entry_review", "when": {"attention": ["elevated"], "price": ["flat"]}}],
        "reportable_stages": ["entry_review"]})
    assert evaluate(x(), s)[0] == "watch"


def test_require_open_quarter_flag(settings):
    closed = x(quarter_open=False)
    assert evaluate(closed, settings)[0] == "entry_review"           # default: information only
    s = load_settings(overrides={"earnings": {"require_open_quarter_for_entry": True}})
    assert evaluate(closed, s)[0] == "watch"
