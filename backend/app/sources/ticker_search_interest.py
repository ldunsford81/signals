"""ticker_search_interest: search interest in "TICKER stock" (retail family, 0–100, snapshots)."""
from __future__ import annotations

from datetime import date

from app.sources.base import Entity, FetchResult, LiveStub, Observation, SnapshotMeta
from app.sources.demo import generators as gen
from app.sources.demo.generators import World


class TickerSearchInterestDemo:
    name = "ticker_search_interest"
    family = "retail"
    entity_type = "company"
    metrics = ["interest_index"]
    rescales_history = True

    def __init__(self, world: World, **_: object) -> None:
        self.world = world

    def required_settings(self) -> list[str]:
        return []

    def fetch(self, entities: list[Entity], start: date, end: date) -> FetchResult:
        out = FetchResult(snapshot=SnapshotMeta(start, end))
        for e in entities:
            raw = gen.company_retail(self.world, e.key)["ticker_search"]
            for ts, v in gen.rescale_window(raw, start, end).items():
                out.observations.append(Observation(e.entity_type, e.key, "interest_index", ts.date(), float(v)))
        return out


class TickerSearchInterestLive(LiveStub):
    """Search interest in "TICKER stock" from the same provider as search_interest (snapshots)."""
    name = "ticker_search_interest"
    family = "retail"
    entity_type = "company"
    metrics = ["interest_index"]
    rescales_history = True
    provider = "Google Trends via a third-party provider"
    settings_keys = ["TRENDS_PROVIDER_API_KEY"]
