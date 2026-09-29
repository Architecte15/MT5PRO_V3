from __future__ import annotations

from dataclasses import dataclass

from app.utils.enums import Direction


@dataclass(frozen=True)
class SimulatedFill:
    price: float
    pnl: float
    reason: str


def check_exit(direction: Direction, entry: float, sl: float, tp: float, bar) -> SimulatedFill | None:
    # Defensive validation: an already-crossed SL is not a valid open position.
    if direction is Direction.BUY and sl >= entry:
        return None
    if direction is Direction.SELL and sl <= entry:
        return None
    high, low = float(bar["high"]), float(bar["low"])
    if direction is Direction.BUY:
        # Conservative: if both SL and TP are touched, assume SL first.
        if low <= sl: return SimulatedFill(sl, sl - entry, "SL")
        if high >= tp: return SimulatedFill(tp, tp - entry, "TP")
    else:
        if high >= sl: return SimulatedFill(sl, entry - sl, "SL")
        if low <= tp: return SimulatedFill(tp, entry - tp, "TP")
    return None
