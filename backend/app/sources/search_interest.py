"""search_interest: product search interest (0–100 index, rescaled per pull, stored as snapshots)."""
from __future__ import annotations

from datetime import date

from app.sources.base import Entity, FetchResult, Observation, SnapshotMeta
from app.sources.demo import generators as gen
from app.sources.demo.generators import World


class SearchInterestDemo:
    name = "search_interest"
    family = "attention"
    entity_type = "product"
    metrics = ["interest_index"]
    rescales_history = True

    def __init__(self, world: World, **_: object) -> None:
        self.world = world

    def required_settings(self) -> list[str]:
        return []

    def fetch(self, entities: list[Entity], start: date, end: date) -> FetchResult:
        out = FetchResult(snapshot=SnapshotMeta(start, end))
        for e in entities:
            raw = gen.product_raw(self.world, e.company_ticker or "", e.name)["search"]
            for ts, v in gen.rescale_window(raw, start, end).items():
                out.observations.append(Observation(e.entity_type, e.key, "interest_index", ts.date(), float(v)))
        return out
