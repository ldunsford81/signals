"""cashtag_mentions: $TICKER mention counts (all names) and unique accounts (post sample, active names only)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from app.sources.base import Entity, FetchResult, Observation
from app.sources.demo import generators as gen
from app.sources.demo.generators import World


class CashtagMentionsDemo:
    name = "cashtag_mentions"
    family = "retail"
    entity_type = "company"
    metrics = ["mention_count", "unique_accounts"]
    rescales_history = False

    def __init__(self, world: World, **_: object) -> None:
        self.world = world

    def required_settings(self) -> list[str]:
        return []

    def fetch(self, entities: list[Entity], start: date, end: date) -> FetchResult:
        out = FetchResult()
        for e in entities:
            df = gen.company_retail(self.world, e.key).loc[pd.Timestamp(start):pd.Timestamp(end)]
            for ts, row in df.iterrows():
                out.observations.append(Observation(e.entity_type, e.key, "mention_count", ts.date(), float(row["mention_count"])))
                if e.in_sample:
                    out.observations.append(Observation(e.entity_type, e.key, "unique_accounts", ts.date(), float(row["unique_accounts"])))
        return out
