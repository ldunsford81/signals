"""The one interface every data source implements.

Adding, swapping or removing a source touches one adapter file, one registry line and one
config entry. Adapters only fetch; the ingest runner stores; the scan only reads storage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Entity:
    entity_type: str            # "product" | "company" | "benchmark"
    key: str                    # product id, company ticker or benchmark ticker
    name: str
    company_ticker: str | None = None
    keywords: tuple[str, ...] = ()
    in_sample: bool = True      # inside the source's sample scope (e.g. cashtag post sample)
    exclusions: tuple[str, ...] = ()


@dataclass
class Observation:
    entity_type: str
    entity_key: str
    metric: str
    obs_date: date
    value: float


@dataclass
class SnapshotMeta:
    """A whole-window pull for sources whose history rescales on every pull."""
    window_start: date
    window_end: date


@dataclass
class FetchResult:
    observations: list[Observation] = field(default_factory=list)
    snapshot: SnapshotMeta | None = None
    warnings: list[str] = field(default_factory=list)


@runtime_checkable
class SourceAdapter(Protocol):
    name: str                 # "search_interest"
    family: str               # "attention" | "price" | "retail" | "catalog"
    entity_type: str          # "product" | "company"
    metrics: list[str]
    rescales_history: bool    # True: each pull is stored as a whole snapshot

    def required_settings(self) -> list[str]: ...
    def fetch(self, entities: list[Entity], start: date, end: date) -> FetchResult: ...


def date_to_value(d: date) -> float:
    """Dates are stored in observations.value as proleptic ordinals."""
    return float(d.toordinal())


def value_to_date(v: float) -> date:
    return date.fromordinal(int(round(v)))
