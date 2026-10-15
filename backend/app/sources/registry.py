"""Source registry: name -> mode -> adapter factory.

Adding a source = one adapter file + one line here + one entry under `sources:` in config.
"""
from __future__ import annotations

from typing import Callable

from app.core.config import Settings, SourceCfg
from app.sources.base import SourceAdapter
from app.sources.cashtag_mentions import CashtagMentionsDemo, CashtagMentionsLive
from app.sources.demo.state import world
from app.sources.earnings import EarningsCsv, EarningsDemo, EarningsLive
from app.sources.price import PriceDemo, PriceLive
from app.sources.search_interest import SearchInterestDemo, SearchInterestLive
from app.sources.social_mentions import SocialMentionsDemo, SocialMentionsLive
from app.sources.ticker_search_interest import TickerSearchInterestDemo, TickerSearchInterestLive

Factory = Callable[[Settings, SourceCfg], SourceAdapter]


def _demo(cls) -> Factory:
    return lambda settings, cfg: cls(world=world(settings), cfg=cfg)


def _plain(cls) -> Factory:
    return lambda settings, cfg: cls(cfg=cfg)


REGISTRY: dict[str, dict[str, Factory]] = {
    "search_interest": {"demo": _demo(SearchInterestDemo), "live": _plain(SearchInterestLive)},
    "social_mentions": {"demo": _demo(SocialMentionsDemo), "live": _plain(SocialMentionsLive)},
    "price": {"demo": _demo(PriceDemo), "live": _plain(PriceLive)},
    "earnings": {"demo": _demo(EarningsDemo), "csv": _plain(EarningsCsv), "live": _plain(EarningsLive)},
    "ticker_search_interest": {"demo": _demo(TickerSearchInterestDemo), "live": _plain(TickerSearchInterestLive)},
    "cashtag_mentions": {"demo": _demo(CashtagMentionsDemo), "live": _plain(CashtagMentionsLive)},
}

# Fixed order: catalog first so earnings are current before anything reads them.
ORDER = ["earnings", "price", "search_interest", "social_mentions", "ticker_search_interest", "cashtag_mentions"]


def source_names(settings: Settings) -> list[str]:
    names = [n for n in ORDER if n in settings.sources]
    return names + [n for n in settings.sources if n not in names]


def build(name: str, settings: Settings) -> SourceAdapter | None:
    """Return the adapter for the configured mode, or None if no implementation exists for it."""
    cfg = settings.sources[name]
    factory = REGISTRY.get(name, {}).get(cfg.mode)
    return factory(settings, cfg) if factory else None
