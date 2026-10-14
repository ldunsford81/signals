"""Earnings timing: days to earnings, the 6–14 week window and the reporting quarter."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core.config import Settings
from app.db.models import Company
from app.signals.store import AsOfView
from app.sources.base import value_to_date

# Earnings dates entered by hand in Admin are stored as observations under this source name.
MANUAL_SOURCE = "earnings_manual"


@dataclass
class EarningsResult:
    status: str                      # inside_window | outside_window | unknown
    next_earnings_date: date | None
    confirmed: bool | None
    fiscal_quarter_end: date | None
    days_to_earnings: int | None
    days_left_in_quarter: int | None
    reason: str | None
    source: str                      # manual | observations | catalog | none

    @property
    def quarter_open(self) -> bool | None:
        return None if self.days_left_in_quarter is None else self.days_left_in_quarter > 0

    def as_dict(self) -> dict:
        return {"status": self.status,
                "next_earnings_date": self.next_earnings_date.isoformat() if self.next_earnings_date else None,
                "confirmed": self.confirmed,
                "fiscal_quarter_end": self.fiscal_quarter_end.isoformat() if self.fiscal_quarter_end else None,
                "days_to_earnings": self.days_to_earnings, "days_left_in_quarter": self.days_left_in_quarter,
                "quarter_open": self.quarter_open, "reason": self.reason, "source": self.source}


def compute_earnings(view: AsOfView, company: Company, settings: Settings) -> EarningsResult:
    """Point in time: the latest earnings observation on or before as_of; else the catalog row."""
    as_of = view.as_of
    man_v, _ = view.latest_value(MANUAL_SOURCE, company.ticker, "next_earnings_date")
    nxt_v, _ = view.latest_value("earnings", company.ticker, "next_earnings_date")
    if man_v is not None and value_to_date(man_v) >= as_of:
        # A date typed in Admin is what the reviewer knows; it wins over the feed until it passes.
        conf_v, _ = view.latest_value(MANUAL_SOURCE, company.ticker, "confirmed")
        fqe_v, _ = view.latest_value(MANUAL_SOURCE, company.ticker, "fiscal_quarter_end")
        nxt, confirmed = value_to_date(man_v), bool(conf_v) if conf_v is not None else None
        fqe, src = (value_to_date(fqe_v) if fqe_v is not None else None), "manual"
    elif nxt_v is not None:
        conf_v, _ = view.latest_value("earnings", company.ticker, "confirmed")
        fqe_v, _ = view.latest_value("earnings", company.ticker, "fiscal_quarter_end")
        nxt, confirmed = value_to_date(nxt_v), bool(conf_v) if conf_v is not None else None
        fqe, src = (value_to_date(fqe_v) if fqe_v is not None else None), "observations"
    else:
        nxt, confirmed, fqe, src = (company.next_earnings_date, company.earnings_date_confirmed,
                                    company.fiscal_quarter_end, "catalog" if company.next_earnings_date else "none")
    days_left = (fqe - as_of).days if fqe else None
    if nxt is None:
        return EarningsResult("unknown", None, None, fqe, None, days_left, "no earnings date", src)
    days = (nxt - as_of).days
    if days < 0:
        return EarningsResult("unknown", nxt, confirmed, fqe, days, days_left,
                              f"earnings date {nxt} is in the past; needs a date update", src)
    lo, hi = settings.earnings.window_days
    status = "inside_window" if lo <= days <= hi else "outside_window"
    return EarningsResult(status, nxt, confirmed, fqe, days, days_left, None, src)
