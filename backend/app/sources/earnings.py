"""earnings: next earnings date, confirmed flag and fiscal quarter end (catalog family).

Dates are stored in observations.value as ordinals (see base.date_to_value). Each day's row is
what the calendar said that day, so replay sees the date that was known at the time.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from app.sources.base import Entity, FetchResult, Observation, date_to_value
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
