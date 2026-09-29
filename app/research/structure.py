"""Market structure events (spec section 5): HH/HL/LH/LL context, BOS, CHOCH.

Swings become usable only at swing_index + strength (the confirming bar is
closed), matching detect_swings' right-side window. An event is emitted on the
close of the bar that breaks a *known* level — never before.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.strategy.market_structure import SwingPoint, classify_structure, detect_swings
from app.utils.enums import SwingType

BOS = "BOS"
CHOCH = "CHOCH"


@dataclass(frozen=True)
class StructureEvent:
    index: int
    timestamp: pd.Timestamp
    kind: str          # BOS / CHOCH
    direction: str     # UP / DOWN
    level: float


def available_swings(swings: list[SwingPoint], i: int, strength: int) -> list[SwingPoint]:
    return [s for s in swings if s.index + strength <= i]


def trend_at(swings: list[SwingPoint], i: int, strength: int) -> str:
    """Structure-based trend label using only swings known at bar i."""
    avail = available_swings(swings, i, strength)
    if len([s for s in avail if s.type is SwingType.HIGH]) < 2 or len([s for s in avail if s.type is SwingType.LOW]) < 2:
        return "NEUTRAL"
    return classify_structure(avail).trend.value


def detect_structure_events(df: pd.DataFrame, swing_strength: int = 2) -> list[StructureEvent]:
    swings = detect_swings(df, swing_strength)
    events: list[StructureEvent] = []
    state = "NEUTRAL"           # structural state: UP / DOWN / NEUTRAL
    cursor = 0
    last_high: SwingPoint | None = None
    last_low: SwingPoint | None = None

    for i in range(len(df)):
        while cursor < len(swings) and swings[cursor].index + swing_strength <= i:
            sp = swings[cursor]
            if sp.type is SwingType.HIGH:
                last_high = sp
            else:
                last_low = sp
            cursor += 1
        close = float(df["close"].iloc[i])
        if last_high is not None and close > last_high.price:
            kind = CHOCH if state == "DOWN" else BOS
            events.append(StructureEvent(i, pd.Timestamp(df.index[i]), kind, "UP", last_high.price))
            state = "UP"
            last_high = None
        elif last_low is not None and close < last_low.price:
            kind = CHOCH if state == "UP" else BOS
            events.append(StructureEvent(i, pd.Timestamp(df.index[i]), kind, "DOWN", last_low.price))
            state = "DOWN"
            last_low = None
    return events
