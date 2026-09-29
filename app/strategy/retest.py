from __future__ import annotations

from dataclasses import dataclass

from app.utils.enums import Direction


@dataclass(frozen=True)
class RetestAnalysis:
    direction: Direction
    level: float
    detected: bool
    invalidated: bool
    bars_since_breakout: int
    reason: str = ""


def detect_retest(df, direction: Direction, level: float, tolerance_points: float, point_size: float, max_bars: int, breakout_index: int) -> RetestAnalysis:
    tolerance = tolerance_points * point_size
    start = max(breakout_index + 1, 0)
    window = df.iloc[start:]
    bars = len(window)
    if bars == 0:
        return RetestAnalysis(direction, level, False, False, 0, "waiting")
    recent = window.tail(max_bars)
    for _, row in recent.iterrows():
        touched = float(row["low"]) <= level + tolerance and float(row["high"]) >= level - tolerance
        if not touched:
            continue
        if direction is Direction.BUY and float(row["close"]) >= level - tolerance:
            return RetestAnalysis(direction, level, True, False, bars, "support retest")
        if direction is Direction.SELL and float(row["close"]) <= level + tolerance:
            return RetestAnalysis(direction, level, True, False, bars, "resistance retest")
        return RetestAnalysis(direction, level, False, True, bars, "failed retest")
    if bars > max_bars:
        return RetestAnalysis(direction, level, False, True, bars, "max retest bars exceeded")
    return RetestAnalysis(direction, level, False, False, bars, "waiting")
