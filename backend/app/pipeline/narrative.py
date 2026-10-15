"""Plain-English wording for the operator views: signal names, status words, verdicts and checks.

The rules and statuses are unchanged; this only decides how they read on screen.
"""
from __future__ import annotations

import re

SIGNAL = {
    "entry_review": {"label": "Entry signal", "side": "buy"},
    "early_recognition": {"label": "Early mover", "side": "buy"},
    "exit_review": {"label": "Exit signal", "side": "sell"},
    "watch": {"label": "Watching", "side": "radar"},
    "data_gap": {"label": "Data gap", "side": "radar"},
    "none": {"label": "Quiet", "side": None},
}

BUZZ_WORD = {"elevated": "Elevated", "normal": "Normal", "seasonal": "Seasonal", "unknown": "Unknown"}
PRICE_WORD = {"flat": "Flat", "early_move": "Moving", "clear_acceleration": "Breaking out", "unknown": "Unknown"}
CHATTER_WORD = {"quiet": "Quiet", "rising": "Rising", "elevated": "Loud", "unknown": "Unknown"}

_LEGAL = r"(,? (Inc\.|plc|AG|Co\.|Corp\.?|Corporation|Ltd\.?|N\.V\.|S\.A\.))+$"


def short_name(name: str) -> str:
    """'Crocs, Inc.' -> 'Crocs'; 'YETI Holdings, Inc.' -> 'YETI'; 'On Holding AG' -> 'On Holding'."""
    n = re.sub(r"\s*\(fictional\)", "", name)
    n = re.sub(_LEGAL, "", n).strip().rstrip(",")
    shorter = re.sub(r",? Holdings?$", "", n).strip()
    if len(shorter) > 3:
        n = shorter
    return n or name


def friendly_reason(reason: str) -> str:
    m = re.match(r"stale: last observation (\S+) is (\d+)d old", reason or "")
    if m:
        return f"data is {m.group(2)} days old (last update {m.group(1)})"
    m = re.match(r"insufficient history: (\d+)d", reason or "")
    if m:
        return f"only {m.group(1)} days of history so far"
    return reason


def join_names(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:+.1f}%"


def signal_label(stage: str, attention: str) -> str:
    if stage == "none" and attention == "seasonal":
        return "Seasonal"
    return SIGNAL.get(stage, SIGNAL["none"])["label"]


def max_ratio(attention_components: dict) -> float | None:
    rs = [s.get("ratio") for s in (attention_components.get("sources") or {}).values()
          if s.get("healthy") and s.get("ratio") is not None]
    return max(rs) if rs else None


def healthy_sources(attention_components: dict) -> tuple[int, int]:
    srcs = (attention_components.get("sources") or {}).values()
    return sum(1 for s in srcs if s.get("healthy")), len(list((attention_components.get("sources") or {}).values()))


def verdict(product: str, stage: str, attention: str, ratio: float | None, days: int | None, price: str,
            rel: float | None, bench: str | None, volume_ratio: float | None, retail: str, dte: int | None,
            earnings_status: str, unknown_reasons: list[str]) -> str:
    r = f"{ratio:.1f}×" if ratio else "above"
    d = f"{days} day{'s' if days != 1 else ''}" if days else "a few days"
    chat = CHATTER_WORD.get(retail, retail).lower()
    earn = f"Earnings are {dte} days out." if earnings_status != "unknown" and dte is not None else \
        "The next earnings date is unknown."
    vol = f" on {volume_ratio:.1f}× normal volume" if volume_ratio and volume_ratio >= 1.3 else ""
    if stage == "entry_review":
        return (f"Buzz for {product} is {r} normal after {d}, but the stock has moved only {pct(rel)} against "
                f"{bench} and retail chatter is {chat}. {earn}")
    if stage == "early_recognition":
        return (f"Buzz for {product} is {r} normal after {d}, and the stock has started to follow "
                f"({pct(rel)} vs {bench}{vol}). Retail chatter is still {chat}. {earn}")
    if stage == "exit_review":
        return (f"Buzz for {product} has been running for {d}, the stock is {pct(rel)} vs {bench}{vol}, and "
                f"retail chatter is {chat}. The move may be getting crowded. {earn}")
    if stage == "watch":
        why = (f"earnings are {dte} days out, outside the entry window" if earnings_status == "outside_window"
               else f"the price is {PRICE_WORD.get(price, price).lower()} ({pct(rel)} vs {bench})")
        return f"Buzz for {product} is {r} normal after {d}, but {why}. Keep an eye on it."
    if stage == "data_gap":
        return (f"Buzz for {product} is elevated, but no signal can be given: "
                f"{'; '.join(unknown_reasons) or 'an input is missing'}.")
    if attention == "seasonal":
        return f"Buzz for {product} is up, but it matches the same weeks last year, so it reads as seasonal."
    tail = " The next earnings date has passed and needs an update in Data & settings." \
        if earnings_status == "unknown" else ""
    if retail in ("rising", "elevated"):
        return f"Retail chatter is {chat} without a matching move in product buzz. Nothing to act on yet.{tail}"
    return f"Nothing unusual: product buzz, price and retail chatter are all in their normal ranges.{tail}"


def checks(stage: str, attention: str, n_healthy: int, n_sources: int, price: str, bench: str | None,
           retail: str, earnings_status: str, window: tuple[int, int]) -> list[dict]:
    """The conditions behind the signal, each marked met or not, in plain words."""
    weeks = f"{round(window[0] / 7)}–{round(window[1] / 7)} weeks"
    buzz = {"label": f"Buzz elevated ({n_healthy} of {n_sources} sources)" if attention == "elevated"
            else f"Buzz {BUZZ_WORD.get(attention, attention).lower()}", "ok": attention == "elevated"}
    price_flat = {"label": "Price data missing" if price == "unknown" else (
                      f"Price flat vs {bench}" if price == "flat" else f"Price {PRICE_WORD.get(price, price).lower()} vs {bench}"),
                  "ok": price == "flat"}
    price_moving = {"label": f"Price moving vs {bench}", "ok": price in ("early_move", "clear_acceleration")}
    quiet = {"label": f"Retail chatter {CHATTER_WORD.get(retail, retail).lower()}", "ok": retail == "quiet"}
    loud = {"label": f"Retail chatter {CHATTER_WORD.get(retail, retail).lower()}", "ok": retail in ("rising", "elevated")}
    earn = {"label": f"Earnings {weeks} out" if earnings_status == "inside_window"
            else ("Earnings date unknown" if earnings_status == "unknown" else f"Earnings outside {weeks}"),
            "ok": earnings_status == "inside_window"}
    if stage == "exit_review":
        return [buzz, price_moving, loud]
    if stage == "early_recognition":
        return [buzz, price_moving, {**quiet, "ok": retail in ("quiet", "rising")}]
    return [buzz, price_flat, quiet, earn]
