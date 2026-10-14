"""social_mentions: product mentions and posts across social platforms (demo; YouTube first when live)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from app.sources.base import Entity, FetchResult, Observation
from app.sources.demo import generators as gen
from app.sources.demo.generators import World


class SocialMentionsDemo:
    name = "social_mentions"
    family = "attention"
    entity_type = "product"
    metrics = ["mentions", "posts"]
    rescales_history = False

    def __init__(self, world: World, **_: object) -> None:
        self.world = world

    def required_settings(self) -> list[str]:
        return []

    def fetch(self, entities: list[Entity], start: date, end: date) -> FetchResult:
        out = FetchResult()
        for e in entities:
            full = gen.product_raw(self.world, e.company_ticker or "", e.name)
            df = full.loc[pd.Timestamp(start):pd.Timestamp(end), ["mentions", "posts"]]
            if df["mentions"].isna().any():
                have = full.loc[:pd.Timestamp(end), "mentions"].dropna()
                last = have.index.max().date() if not have.empty else None
                out.warnings.append(f"{e.name}: feed returned no data after {last}")
            for ts, row in df.dropna().iterrows():
                for m in self.metrics:
                    out.observations.append(Observation(e.entity_type, e.key, m, ts.date(), float(row[m])))
        return out
