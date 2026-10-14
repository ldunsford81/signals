"""Where the demo anchor date lives.

The anchor is resolved once at seed time (config `demo.anchor_date`, else the last completed
US trading session) and written to data/demo_state.json, so later ingests extend the same
deterministic history instead of shifting it. Re-seed with --reset to move the demo to today.
"""
from __future__ import annotations

import json
from datetime import date

from app.core import calendar
from app.core.config import Settings
from app.core.paths import data_dir
from app.sources.demo.generators import World


def _state_file():
    return data_dir() / "demo_state.json"


def stored_anchor() -> date | None:
    try:
        return date.fromisoformat(json.loads(_state_file().read_text())["anchor_date"])
    except (FileNotFoundError, KeyError, ValueError):
        return None


def store_anchor(anchor: date) -> None:
    _state_file().write_text(json.dumps({"anchor_date": anchor.isoformat()}))


def resolve_anchor(settings: Settings) -> date:
    if settings.demo.anchor_date:
        return calendar.session_on_or_before(settings.demo.anchor_date)
    return stored_anchor() or calendar.last_completed_session()


def world(settings: Settings) -> World:
    return World(resolve_anchor(settings), settings.demo.history_days, settings.demo.random_seed)
