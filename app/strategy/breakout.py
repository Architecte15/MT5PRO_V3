from __future__ import annotations

from dataclasses import dataclass

from app.strategy.trendline import Trendline
from app.utils.enums import Direction


@dataclass(frozen=True)
class BreakoutAnalysis:
    direction: Direction
    index: int
    close: float
    level: float
    buffer: float
    confirmed: bool


def detect_breakout(df, trendline: Trendline, direction: Direction, buffer_points: float, point_size: float, lookback_bars: int = 1) -> BreakoutAnalysis | None:
    if trendline is None or not trendline.validity or len(df) == 0:
        return None
    if lookback_bars <= 0:
        return None
    start = max(0, len(df) - lookback_bars)
    confirmed_row = None
    idx = None
    level = None
    for candidate_idx in range(start, len(df)):
        candidate = df.iloc[candidate_idx]
        candidate_level = trendline.projected_value(candidate_idx)
        if direction is Direction.BUY:
            is_confirmed = float(candidate["close"]) > candidate_level + buffer_points * point_size
        else:
            is_confirmed = float(candidate["close"]) < candidate_level - buffer_points * point_size
        if is_confirmed:
            confirmed_row = candidate
            idx = candidate_idx
            level = candidate_level
            break
    if confirmed_row is None or idx is None or level is None:
        return None
    row = confirmed_row
    buffer = buffer_points * point_size
    if direction is Direction.BUY:
        confirmed = float(row["close"]) > level + buffer
    else:
        confirmed = float(row["close"]) < level - buffer
    return BreakoutAnalysis(direction, idx, float(row["close"]), float(level), buffer, confirmed) if confirmed else None
