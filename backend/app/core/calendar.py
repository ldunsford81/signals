"""US exchange trading calendar (offline, via exchange_calendars XNYS).

All `as_of` dates are NYSE session dates. Price/volume windows and evaluation horizons
count trading days; search/social/cashtag windows count calendar days.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from functools import lru_cache

import exchange_calendars as xc
import pandas as pd


@lru_cache(maxsize=1)
def _cal():
    return xc.get_calendar("XNYS")


def is_session(d: date) -> bool:
    cal = _cal()
    ts = pd.Timestamp(d)
    if ts < cal.first_session or ts > cal.last_session:
        return False
    return bool(cal.is_session(ts))


def session_on_or_before(d: date) -> date:
    cal = _cal()
    ts = min(pd.Timestamp(d), cal.last_session)
    return cal.date_to_session(ts, direction="previous").date()


def session_on_or_after(d: date) -> date:
    cal = _cal()
    return cal.date_to_session(pd.Timestamp(d), direction="next").date()


def last_completed_session(now: datetime | None = None) -> date:
    """Most recent NYSE session whose close is at or before `now` (UTC)."""
    cal = _cal()
    now = now or datetime.now(timezone.utc)
    now_ts = pd.Timestamp(now).tz_convert("UTC") if pd.Timestamp(now).tzinfo else pd.Timestamp(now, tz="UTC")
    s = cal.date_to_session(pd.Timestamp(now_ts.date()), direction="previous")
    if cal.session_close(s) > now_ts:
        s = cal.previous_session(s)
    return s.date()


def sessions_between(start: date, end: date) -> list[date]:
    cal = _cal()
    lo, hi = max(pd.Timestamp(start), cal.first_session), min(pd.Timestamp(end), cal.last_session)
    if lo > hi:
        return []
    return [s.date() for s in cal.sessions_in_range(lo, hi)]


def add_sessions(d: date, n: int) -> date:
    """The session n trading days after (n>0) or before (n<0) session-or-previous of d."""
    cal = _cal()
    s = cal.date_to_session(pd.Timestamp(d), direction="previous")
    return cal.session_offset(s, n).date()
