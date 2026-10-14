"""The demo universe: 12 companies, their products, and the planted scenarios.

Real tickers are used for realism, but every number attached to them is synthetic.
All offsets are calendar days relative to the demo anchor date (negative = in the past).

Scenario numbers refer to the "Required scenarios on the anchor date" table in the build prompt.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Bump:
    """Multiplier on an attention or retail series.

    kind: step     ramp over 2 days to `mult`, hold until `end` (default: forever)
          exp      exponential growth from 1 to `mult` over [start, 0], hold afterwards
          spike    single day at `start`
          episode  ramp 7 days, hold `hold` days, decay 10 days
    """
    start: int
    kind: str = "step"
    mult: float = 2.6
    end: int | None = None
    hold: int = 21
    sources: tuple[str, ...] = ("search", "social")
    unique_mult: float | None = None   # cashtag only: multiplier on unique accounts (defaults to mult)


@dataclass(frozen=True)
class PriceMove:
    """Bend the idiosyncratic price path so it returns `rel` over sessions in [start, end]."""
    start: int
    end: int
    rel: float
    calm: bool = False            # replace noise in the window with very low volatility
    volume_mult: float = 1.0
    volume_from: int | None = None  # volume multiplier applies from this offset (default start)


@dataclass(frozen=True)
class ProductSpec:
    name: str
    keywords: tuple[str, ...]
    base_search: float = 40.0
    base_social: float = 120.0
    bumps: tuple[Bump, ...] = ()
    social_ends: int | None = None      # social feed for this product stops after this offset
    launched_offset: int = -900
    scenario: str | None = None


@dataclass(frozen=True)
class CompanySpec:
    ticker: str
    name: str
    sector: str
    benchmark: str
    market_cap_usd_m: float
    analyst_count: int
    products: tuple[ProductSpec, ...]
    earnings_in_days: int = 60          # next earnings, days after anchor
    quarter_lag: int = 45               # earnings date minus fiscal quarter end
    earnings_stale_from: int | None = None  # earnings source stops updating after this offset
    base_price: float = 50.0
    base_volume: float = 1_500_000
    price_moves: tuple[PriceMove, ...] = ()
    price_ends: int | None = None       # price feed for this ticker stops after this offset
    retail_bumps: tuple[Bump, ...] = ()  # sources: "ticker_search", "cashtag"
    base_ticker_search: float = 30.0
    base_cashtag: float = 30.0
    exchange: str = "NYSE"
    is_demo: bool = False
    notes: str | None = None
    scenario: str | None = None


BENCHMARKS = {"XLY": 190.0, "XRT": 75.0, "IJH": 60.0}

FLAT = PriceMove(-45, 0, 0.004, calm=True)


def _p(name: str, *kw: str, **extra) -> ProductSpec:
    return ProductSpec(name=name, keywords=tuple(kw) or (name.lower(),), **extra)


def lead_episode(start: int, lag: int) -> tuple[Bump, list[PriceMove], list[Bump]]:
    """Attention leads price by `lag` days; price runs +12% then gives some back; retail follows price."""
    att = Bump(start, "episode", 3.0, hold=21)
    p0 = start + lag
    moves = [PriceMove(p0, p0 + 21, 0.12, volume_mult=1.6), PriceMove(p0 + 22, p0 + 42, -0.05)]
    retail = [Bump(p0 + 12, "step", 2.0, end=p0 + 24, sources=("ticker_search",)),
              Bump(p0 + 12, "step", 2.2, end=p0 + 24, sources=("cashtag",))]
    return att, moves, retail


def no_lead_episode(start: int) -> tuple[Bump, list[PriceMove], list[Bump]]:
    """Attention spikes but the stock never follows (drifts down)."""
    return Bump(start, "episode", 3.0, hold=21), [PriceMove(start + 7, start + 35, -0.04)], []


# Historical episodes for replay: (ticker, product index, episode)
EPISODES = {
    ("SONO", 1): lead_episode(-330, 14),
    ("BOOT", 1): no_lead_episode(-310),
    ("CROX", 1): lead_episode(-290, 28),
    ("YETI", 1): no_lead_episode(-265),
    ("ELF", 1): lead_episode(-250, 35),
    ("FIVE", 0): lead_episode(-225, 21),
    ("ZDMO", 0): no_lead_episode(-205),
    ("COTY", 1): lead_episode(-190, 42),
    ("WRBY", 1): no_lead_episode(-165),
    ("OLPX", 1): lead_episode(-155, 14),
}

ENTRY = Bump(-12, "step", 2.6)

_COMPANIES: list[CompanySpec] = [
    CompanySpec(
        "CROX", "Crocs, Inc.", "apparel", "XLY", 6200, 12,
        (_p("Charm clog collab", "crocs charm clog", "crocs collab"),
         _p("Echo slide", "crocs echo slide"),
         _p("Kids lined clog", "crocs lined clog kids")),
        earnings_in_days=70, quarter_lag=45, base_price=95, price_moves=(FLAT,),
        scenario="1: entry_review",
    ),
    CompanySpec(
        "ONON", "On Holding AG", "apparel", "XLY", 15000, 22,
        (_p("Cloudtilt trainer", "on cloudtilt"), _p("Cloudsurfer trail", "on cloudsurfer trail")),
        earnings_in_days=30, base_price=48,
        price_moves=(PriceMove(-60, -26, 0.0, calm=True), PriceMove(-25, 0, 0.06, calm=True, volume_mult=1.8, volume_from=-10)),
        retail_bumps=(Bump(-2, "step", 1.9, sources=("ticker_search",)), Bump(-2, "step", 2.0, sources=("cashtag",))),
        scenario="2: exit_review",
    ),
    CompanySpec(
        "ELF", "e.l.f. Beauty, Inc.", "beauty", "XLY", 5800, 15,
        (_p("Glow reviver lip oil", "elf lip oil"), _p("Power grip primer", "elf power grip primer"),
         _p("Halo glow filter", "elf halo glow")),
        earnings_in_days=20, base_price=110,
        price_moves=(PriceMove(-60, -15, 0.0, calm=True), PriceMove(-14, 0, 0.055, calm=True)),
        scenario="3: early_recognition",
    ),
    CompanySpec(
        "YETI", "YETI Holdings, Inc.", "consumer hardware", "XLY", 3300, 14,
        (_p("Hopper backpack cooler", "yeti hopper backpack"), _p("Rambler tumbler colors", "yeti rambler colors")),
        earnings_in_days=60, base_price=40, price_moves=(FLAT,),
        scenario="4: seasonal",
    ),
    CompanySpec(
        "SONO", "Sonos, Inc.", "consumer hardware", "XLY", 1700, 9,
        (_p("Ace headphones", "sonos ace"), _p("Arc soundbar", "sonos arc")),
        earnings_in_days=45, base_price=14,
        scenario="5: one-day spike",
    ),
    CompanySpec(
        "BOOT", "Boot Barn Holdings, Inc.", "specialty retail", "XRT", 4300, 10,
        (_p("Western work boot", "boot barn work boot"), _p("Cody James denim", "cody james jeans")),
        earnings_in_days=55, base_price=140,
        retail_bumps=(Bump(-2, "step", 4.0, sources=("cashtag",), unique_mult=1.1),),
        scenario="6: cashtag burst from few accounts",
    ),
    CompanySpec(
        "BIRK", "Birkenstock Holding plc", "apparel", "XLY", 9800, 16,
        (_p("Boston clog suede", "birkenstock boston clog"), _p("Arizona EVA", "birkenstock arizona eva")),
        earnings_in_days=70, base_price=52, price_moves=(FLAT,), price_ends=-6,
        scenario="7: stale price feed",
    ),
    CompanySpec(
        "WRBY", "Warby Parker Inc.", "specialty retail", "XRT", 2400, 11,
        (_p("Contact lens subscription", "warby parker contacts"), _p("Kids frames", "warby parker kids")),
        earnings_in_days=65, base_price=22, price_moves=(FLAT,),
        scenario="8: single attention source",
    ),
    CompanySpec(
        "COTY", "Coty Inc.", "beauty", "XLY", 5200, 13, ( _p("Burberry Goddess fragrance", "burberry goddess"),
         _p("CoverGirl clean foundation", "covergirl clean")),
        earnings_in_days=50, quarter_lag=60, base_price=7.5, price_moves=(FLAT,),
        scenario="9: reporting quarter closed",
    ),
    CompanySpec(
        "OLPX", "Olaplex Holdings, Inc.", "beauty", "IJH", 1100, 8,
        (_p("No.4 bond shampoo", "olaplex no 4"), _p("Bond oil", "olaplex oil")),
        earnings_in_days=150, base_price=1.8, price_moves=(FLAT,),
        scenario="10: earnings too far",
    ),
    CompanySpec(
        "FIVE", "Five Below, Inc.", "specialty retail", "XRT", 5100, 18,
        (_p("Five Beyond toys", "five below toys"), _p("Room decor", "five below decor")),
        earnings_in_days=-12, earnings_stale_from=-12, base_price=95,
        scenario="11: earnings date in the past",
    ),
    CompanySpec(
        "ZDMO", "Demo Outfitters Co. (fictional)", "specialty retail", "IJH", 800, 4,
        (_p("Trail mule", "demo trail mule"), _p("Puffer tote", "demo puffer tote")),
        earnings_in_days=80, base_price=18, exchange="DEMO", is_demo=True,
        notes="Fictional company for demos; not a real ticker.",
        scenario="12: flat",
    ),
]


def _with_scenario_products() -> list[CompanySpec]:
    """Attach product-level scenarios and historical episodes to the first/second products."""
    product_bumps: dict[tuple[str, int], dict] = {
        ("CROX", 0): {"bumps": (ENTRY,), "scenario": "1: entry_review"},
        ("ONON", 0): {"bumps": (Bump(-35, "exp", 4.0),), "scenario": "2: exit_review"},
        ("ELF", 0): {"bumps": (Bump(-16, "step", 2.6),), "scenario": "3: early_recognition"},
        ("YETI", 0): {"bumps": (Bump(-14, "step", 2.5), Bump(-379, "step", 2.5, end=-330)),
                      "scenario": "4: seasonal"},
        ("SONO", 0): {"bumps": (Bump(-3, "spike", 5.0, sources=("search",)),), "scenario": "5: one-day spike"},
        ("BIRK", 0): {"bumps": (ENTRY,), "scenario": "7: data_gap (stale price)"},
        ("WRBY", 0): {"bumps": (ENTRY,), "social_ends": -10, "scenario": "8: entry_review single_source"},
        ("COTY", 0): {"bumps": (ENTRY,), "scenario": "9: entry_review quarter closed"},
        ("OLPX", 0): {"bumps": (Bump(-12, "step", 2.8),), "scenario": "10: watch (150 days to earnings)"},
    }
    out: list[CompanySpec] = []
    for c in _COMPANIES:
        products = []
        moves = list(c.price_moves)
        retail = list(c.retail_bumps)
        for i, p in enumerate(c.products):
            kw = dict(product_bumps.get((c.ticker, i), {}))
            bumps = list(kw.pop("bumps", ()))
            if (c.ticker, i) in EPISODES:
                att, ep_moves, ep_retail = EPISODES[(c.ticker, i)]
                bumps.append(att)
                moves.extend(ep_moves)
                retail.extend(ep_retail)
            products.append(ProductSpec(name=p.name, keywords=p.keywords, base_search=p.base_search + 4 * i,
                                        base_social=p.base_social + 15 * i, bumps=tuple(bumps),
                                        launched_offset=-900 + 60 * i, **kw))
        out.append(CompanySpec(**{**c.__dict__, "products": tuple(products), "price_moves": tuple(moves),
                                  "retail_bumps": tuple(retail)}))
    return out


COMPANIES: list[CompanySpec] = _with_scenario_products()
BY_TICKER: dict[str, CompanySpec] = {c.ticker: c for c in COMPANIES}

# Hand-entered timeline events for the demo: (ticker, product index or None, offset, type, title)
ANNOUNCEMENTS = [
    ("CROX", 0, -13, "partnership", "Charm clog collab announced with streetwear label"),
    ("ONON", 0, -36, "new_product", "Cloudtilt trainer colourway drop"),
    ("ONON", None, -9, "distribution", "Expanded wholesale distribution in Asia"),
    ("ELF", 0, -17, "new_product", "Glow reviver lip oil new shades"),
    ("WRBY", 0, -12, "distribution", "Contact lens subscription opens in two new states"),
    ("COTY", 0, -14, "partnership", "Burberry Goddess celebrity campaign"),
    ("YETI", 0, -15, "new_product", "Hopper backpack cooler fall colours"),
    ("FIVE", None, -40, "negative_event", "Store closures in two regions"),
]

# Expected stage per scenario product on the anchor date (used by the end-to-end test and the README).
EXPECTED = {
    ("CROX", "Charm clog collab"): {"stage": "entry_review"},
    ("ONON", "Cloudtilt trainer"): {"stage": "exit_review"},
    ("ELF", "Glow reviver lip oil"): {"stage": "early_recognition"},
    ("YETI", "Hopper backpack cooler"): {"stage": "none", "attention": "seasonal"},
    ("SONO", "Ace headphones"): {"stage": "none", "attention": "normal"},
    ("BOOT", "Western work boot"): {"stage": "none", "retail": "rising"},
    ("BIRK", "Boston clog suede"): {"stage": "data_gap", "price": "unknown"},
    ("WRBY", "Contact lens subscription"): {"stage": "entry_review", "single_source": True},
    ("COTY", "Burberry Goddess fragrance"): {"stage": "entry_review", "quarter_closed": True},
    ("OLPX", "No.4 bond shampoo"): {"stage": "watch"},
    ("FIVE", "Five Beyond toys"): {"stage": "none", "earnings_unknown": True},
    ("ZDMO", "Trail mule"): {"stage": "none", "attention": "normal"},
}
