"""Stage rule engine. Rules come from config and are evaluated top to bottom; first match wins.

A stage is a rule over the three signal statuses plus earnings timing. Nothing is blended into a
score. Hard invariant: entry_review never fires when any input is `unknown`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core.config import Settings, StageRule

NO_STAGE = "none"


@dataclass
class StageInputs:
    as_of: date
    attention: str
    price: str
    retail: str
    earnings: str                      # inside_window | outside_window | unknown
    last_elevated_date: date | None
    quarter_open: bool | None

    def family(self, name: str) -> str:
        return {"attention": self.attention, "price": self.price, "retail": self.retail,
                "earnings": self.earnings}[name]

    def any_unknown(self) -> bool:
        return "unknown" in (self.attention, self.price, self.retail, self.earnings)


def matches(rule: StageRule, x: StageInputs, settings: Settings) -> bool:
    w = rule.when
    if w.attention_elevated_within_days is not None:
        if x.last_elevated_date is None or (x.as_of - x.last_elevated_date).days > w.attention_elevated_within_days:
            return False
    if w.any_required_unknown is not None and not any(x.family(f) == "unknown" for f in w.any_required_unknown):
        return False
    if w.attention is not None and x.attention not in w.attention:
        return False
    if w.price is not None and x.price not in w.price:
        return False
    if w.retail is not None and x.retail not in w.retail:
        return False
    if w.earnings is not None and x.earnings != w.earnings:
        return False
    if w.quarter_open is not None and x.quarter_open is not w.quarter_open:
        return False
    if rule.name == "entry_review":
        if x.any_unknown():
            return False
        if settings.earnings.require_open_quarter_for_entry and x.quarter_open is not True:
            return False
    return True


def evaluate(x: StageInputs, settings: Settings) -> tuple[str, int | None]:
    """Return (stage name, index of the rule that fired) or (NO_STAGE, None)."""
    for i, rule in enumerate(settings.stages):
        if matches(rule, x, settings):
            return rule.name, i
    return NO_STAGE, None
