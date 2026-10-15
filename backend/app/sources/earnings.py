"""earnings: next earnings date, confirmed flag and fiscal quarter end (catalog family).

Dates are stored in observations.value as ordinals (see base.date_to_value). Each day's row is
what the calendar said that day, so replay sees the date that was known at the time.
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pandas as pd

from app.sources.base import Entity, FetchResult, LiveStub, Observation, date_to_value
from app.sources.demo import generators as gen
from app.sources.demo.generators import World

METRICS = ["next_earnings_date", "confirmed", "fiscal_quarter_end"]


class EarningsDemo:
    name = "earnings"
    family = "catalog"
    entity_type = "company"
    metrics = METRICS
    rescales_history = False

    def __init__(self, world: World, **_: object) -> None:
        self.world = world

    def required_settings(self) -> list[str]:
        return []

    def fetch(self, entities: list[Entity], start: date, end: date) -> FetchResult:
        out = FetchResult()
        for e in entities:
            df = gen.company_earnings(self.world, e.key).loc[pd.Timestamp(start):pd.Timestamp(end)]
            for ts, row in df.iterrows():
                d = ts.date()
                out.observations += [
                    Observation(e.entity_type, e.key, "next_earnings_date", d, date_to_value(row["next_earnings_date"])),
                    Observation(e.entity_type, e.key, "confirmed", d, float(bool(row["confirmed"]))),
                    Observation(e.entity_type, e.key, "fiscal_quarter_end", d, date_to_value(row["fiscal_quarter_end"])),
                ]
        return out


class EarningsLive(LiveStub):
    """Earnings calendar API. Dates move until confirmed: keep the confirmed flag from the provider."""
    name = "earnings"
    family = "catalog"
    entity_type = "company"
    metrics = METRICS
    provider = "an earnings calendar API"
    settings_keys = ["EARNINGS_CALENDAR_API_KEY"]


class EarningsCsv:
    """Earnings from a checked-in CSV (config: `earnings: {mode: csv, csv: data/earnings.csv}`).

    Columns: ticker, next_earnings_date, confirmed (yes/no), fiscal_quarter_end, as_of (optional).
    `as_of` is the date the row was known; rows without it are stamped with the ingest date. Several
    rows per ticker keep a point-in-time history, so replay sees the date that was known then.
    """
    name = "earnings"
    family = "catalog"
    entity_type = "company"
    metrics = METRICS
    rescales_history = False

    def __init__(self, cfg=None, **_: object) -> None:
        from app.core.paths import REPO_ROOT
        rel = getattr(cfg, "csv", None) or "data/earnings.csv"
        p = Path(rel)
        self.path = p if p.is_absolute() else REPO_ROOT / p

    def required_settings(self) -> list[str]:
        return []

    def fetch(self, entities: list[Entity], start: date, end: date) -> FetchResult:
        out = FetchResult()
        wanted = {e.key for e in entities}
        seen: set[str] = set()
        with self.path.open(newline="") as f:          # a missing file raises: the run is recorded as error
            reader = csv.DictReader(f)
            for line, row in enumerate(reader, start=2):
                row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
                ticker = row.get("ticker", "").upper()
                if ticker not in wanted:
                    continue
                try:
                    nxt = date.fromisoformat(row["next_earnings_date"])
                    fqe = date.fromisoformat(row["fiscal_quarter_end"]) if row.get("fiscal_quarter_end") else None
                    known = date.fromisoformat(row["as_of"]) if row.get("as_of") else end
                    confirmed = row.get("confirmed", "").lower() in ("1", "true", "yes", "y")
                except (KeyError, ValueError) as e:
                    out.warnings.append(f"{self.path.name} line {line}: {e}")
                    continue
                if known > end:
                    continue
                seen.add(ticker)
                out.observations += [
                    Observation("company", ticker, "next_earnings_date", known, date_to_value(nxt)),
                    Observation("company", ticker, "confirmed", known, float(confirmed)),
                ]
                if fqe:
                    out.observations.append(Observation("company", ticker, "fiscal_quarter_end", known, date_to_value(fqe)))
        missing = sorted(wanted - seen)
        if missing:
            out.warnings.append(f"no earnings row in {self.path.name} for {', '.join(missing)}")
        return out
