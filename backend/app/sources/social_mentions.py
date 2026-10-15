"""social_mentions: product mentions and posts across social platforms (demo; YouTube first when live)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from app.sources.base import Entity, FetchResult, LiveStub, Observation
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


class SocialMentionsLive(LiveStub):
    """YouTube Data API first (search.list per product keyword, counted per day).

    The daily quota limits searches per day: check the current quota and keep the watchlist small
    or set `scope: active_only`. Reddit's API closes to new developers on 31 Oct 2026; only add it
    with an approved application.
    """
    name = "social_mentions"
    family = "attention"
    entity_type = "product"
    metrics = ["mentions", "posts"]
    provider = "YouTube Data API"
    settings_keys = ["YOUTUBE_API_KEY"]
