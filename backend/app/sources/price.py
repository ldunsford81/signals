"""price: daily close and volume for companies and benchmarks (trading days only)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from app.core import calendar

from app.sources.base import Entity, FetchResult, Observation
from app.sources.demo import generators as gen
from app.sources.demo.generators import World


class PriceDemo:
    name = "price"
    family = "price"
    entity_type = "company"
    metrics = ["close", "volume"]
    rescales_history = False

    def __init__(self, world: World, **_: object) -> None:
        self.world = world

    def required_settings(self) -> list[str]:
        return []

    def fetch(self, entities: list[Entity], start: date, end: date) -> FetchResult:
        out = FetchResult()
        for e in entities:
            if e.entity_type == "benchmark":
                df = gen.benchmark_prices(self.world, e.key)
            else:
                df = gen.company_prices(self.world, e.key)
            win = df.loc[pd.Timestamp(start):pd.Timestamp(end)]
            last = df.index.max().date() if not df.empty else None
            if last is None or last < calendar.session_on_or_before(end):
                out.warnings.append(f"{e.key}: feed returned no bars after {last}")
            for ts, row in win.iterrows():
                for m in self.metrics:
                    out.observations.append(Observation(e.entity_type, e.key, m, ts.date(), float(row[m])))
        return out
