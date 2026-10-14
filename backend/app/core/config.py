"""Config loading, validation and hashing.

The YAML file is validated with Pydantic on every load. An invalid config raises
ConfigError with a readable message and nothing downstream runs.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.core.paths import config_path

Mode = Literal["demo", "live", "csv", "off"]
Family = Literal["price", "retail", "earnings", "attention"]


class ConfigError(Exception):
    pass


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DemoCfg(Strict):
    anchor_date: date | None = None
    history_days: int = 400
    random_seed: int = 20261014


class EarningsCfg(Strict):
    window_days: tuple[int, int] = (42, 98)
    require_open_quarter_for_entry: bool = False


class HealthCfg(Strict):
    max_staleness_days: dict[str, int]
    min_history_days: dict[str, int]
    min_baseline_index: float = 5

    @field_validator("min_history_days")
    @classmethod
    def _families(cls, v: dict[str, int]) -> dict[str, int]:
        missing = {"attention", "price", "retail"} - set(v)
        if missing:
            raise ValueError(f"min_history_days missing {sorted(missing)}")
        return v


class SeriesRef(Strict):
    source: str
    metric: str
    sparse_floor: bool = False          # apply health.min_baseline_index (0–100 index series)
    breadth_metric: str | None = None   # cashtag unique-accounts check


class PriceFamily(Strict):
    close: SeriesRef
    volume: SeriesRef


class FamiliesCfg(Strict):
    attention: list[SeriesRef]
    price: PriceFamily
    retail: list[SeriesRef]


class RatioZ(Strict):
    min_ratio: float
    min_z: float


class Persistence(Strict):
    days_required: int = 4
    of_last: int = 5


class Seasonality(Strict):
    min_history_days: int = 365
    min_yoy_ratio: float = 1.2


class AttentionCfg(Strict):
    short_window: int = 7
    baseline_window: tuple[int, int] = (8, 56)
    accelerating: RatioZ
    persistence: Persistence = Persistence()
    min_accelerating_sources: int = 2
    allow_single_source_when_only_one_healthy: bool = True
    seasonality: Seasonality = Seasonality()
    signal_lookback_days: int = 90
    announcement_lookback_days: int = 14


class PriceThreshold(Strict):
    min_relative_return: float
    min_volume_ratio: float


class PriceResponseCfg(Strict):
    no_signal_lookback_days: int = 20
    volume_ratio_windows: tuple[int, int] = (5, 60)
    early_move: PriceThreshold
    clear_acceleration: PriceThreshold


class RetailCfg(Strict):
    short_window: int = 3
    baseline_window: tuple[int, int] = (4, 30)
    rising: RatioZ
    elevated: RatioZ
    cashtag_min_unique_account_ratio: float = 1.3


ATTENTION_VALUES = {"elevated", "normal", "seasonal", "unknown"}
PRICE_VALUES = {"flat", "early_move", "clear_acceleration", "unknown"}
RETAIL_VALUES = {"quiet", "rising", "elevated", "unknown"}


class StageWhen(Strict):
    attention_elevated_within_days: int | None = None
    any_required_unknown: list[Family] | None = None
    attention: list[str] | None = None
    price: list[str] | None = None
    retail: list[str] | None = None
    earnings: Literal["inside_window", "outside_window", "unknown"] | None = None
    quarter_open: bool | None = None

    @model_validator(mode="after")
    def _values(self) -> "StageWhen":
        for name, allowed in (("attention", ATTENTION_VALUES), ("price", PRICE_VALUES), ("retail", RETAIL_VALUES)):
            vals = getattr(self, name)
            if vals is not None and not set(vals) <= allowed:
                raise ValueError(f"{name} values {sorted(set(vals) - allowed)} not in {sorted(allowed)}")
        return self


class StageRule(Strict):
    name: str
    when: StageWhen


class EvaluationCfg(Strict):
    horizons_trading_days: list[int] = [5, 20, 60]
    include_through_earnings: bool = True
    dedupe_days: int = 30
    min_sample_to_judge: int = 20
    hit: dict[str, str]


class IngestCfg(Strict):
    timeout_seconds: int = 120
    overlap_days: int = 3
    default_lookback_days: int = 14


class SourceCfg(BaseModel):
    # Sources may carry adapter-specific keys (benchmarks, csv path, budget), so extra is allowed.
    model_config = ConfigDict(extra="allow")
    mode: Mode = "demo"
    scope: Literal["watchlist", "active_only"] = "watchlist"
    sample_scope: Literal["watchlist", "active_only"] | None = None
    monthly_budget_usd: float | None = None
    snapshot_window_days: int | None = None
    benchmarks: list[str] = []
    csv: str | None = None


class ScheduleCfg(Strict):
    in_process_enabled: bool = False
    cron_local: str = "30 8 * * 2-6"
    timezone: str = "Australia/Sydney"


class Settings(Strict):
    demo: DemoCfg = DemoCfg()
    earnings: EarningsCfg = EarningsCfg()
    health: HealthCfg
    families: FamiliesCfg
    attention: AttentionCfg
    price_response: PriceResponseCfg
    retail: RetailCfg
    stages: list[StageRule]
    reportable_stages: list[str] = ["entry_review", "early_recognition", "exit_review"]
    stage_priority: list[str] = ["exit_review", "entry_review", "early_recognition", "watch", "data_gap", "none"]
    evaluation: EvaluationCfg
    ingest: IngestCfg = IngestCfg()
    sources: dict[str, SourceCfg]
    schedule: ScheduleCfg = ScheduleCfg()

    @model_validator(mode="after")
    def _cross_checks(self) -> "Settings":
        names = [r.name for r in self.stages]
        if len(names) != len(set(names)):
            raise ValueError("stage names must be unique")
        for s in self.reportable_stages:
            if s not in names:
                raise ValueError(f"reportable stage '{s}' has no rule in stages")
        refs = [*self.families.attention, *self.families.retail, self.families.price.close]
        for ref in refs:
            if ref.source not in self.sources:
                raise ValueError(f"family references unknown source '{ref.source}'")
        return self

    # ---- helpers -------------------------------------------------------
    def staleness(self, source: str) -> int:
        return self.health.max_staleness_days.get(source, 7)

    def hash(self) -> str:
        return config_hash(self)

    def canonical(self) -> dict:
        return self.model_dump(mode="json")


def config_hash(settings: Settings) -> str:
    blob = json.dumps(settings.canonical(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def load_settings(path: Path | str | None = None, overrides: dict | None = None) -> Settings:
    p = Path(path) if path else config_path()
    try:
        raw = yaml.safe_load(p.read_text())
    except FileNotFoundError as e:
        raise ConfigError(f"Config file not found: {p}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"Config file {p} is not valid YAML: {e}") from e
    if not isinstance(raw, dict):
        raise ConfigError(f"Config file {p} must be a mapping at the top level")
    if overrides:
        raw = deep_merge(raw, overrides)
    try:
        return Settings.model_validate(raw)
    except ValidationError as e:
        lines = [f"Invalid config {p}:"]
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            lines.append(f"  - {loc}: {err['msg']}")
        raise ConfigError("\n".join(lines)) from e


def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out
