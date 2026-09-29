from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.strategy.market_structure import SwingPoint
from app.utils.enums import Direction, SwingType


@dataclass(frozen=True)
class Trendline:
    point_1: SwingPoint
    point_2: SwingPoint
    slope: float
    intercept: float
    direction: Direction
    validity: bool
    creation_time: object

    def value_at(self, index: float) -> float:
        return self.slope * index + self.intercept

    def projected_value(self, index: float) -> float:
        return self.value_at(index)


def _line(p1: SwingPoint, p2: SwingPoint) -> tuple[float, float]:
    if p2.index == p1.index:
        raise ValueError("Trendline points must have different indexes")
    slope = (p2.price - p1.price) / (p2.index - p1.index)
    intercept = p1.price - slope * p1.index
    return slope, intercept


def build_trendline(swings: Sequence[SwingPoint], direction: Direction) -> Trendline | None:
    wanted = SwingType.LOW if direction is Direction.BUY else SwingType.HIGH
    pts = [s for s in swings if s.type is wanted and s.confirmed]
    if len(pts) < 2:
        return None
    p1, p2 = pts[-2], pts[-1]
    slope, intercept = _line(p1, p2)
    # For a support line we favor an upward or stable slope; for resistance, downward or stable.
    validity = slope >= 0 if direction is Direction.BUY else slope <= 0
    return Trendline(p1, p2, slope, intercept, direction, validity, p2.timestamp)
