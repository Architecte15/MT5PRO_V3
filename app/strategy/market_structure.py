from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pandas as pd

from app.utils.enums import StructureType, SwingType, Trend


@dataclass(frozen=True)
class SwingPoint:
    timestamp: pd.Timestamp
    price: float
    index: int
    type: SwingType
    confirmed: bool


@dataclass(frozen=True)
class StructureAnalysis:
    trend: Trend
    last_label: StructureType
    points: tuple[SwingPoint, ...]
    bullish: bool
    bearish: bool


def detect_swings(df: pd.DataFrame, strength: int = 2) -> list[SwingPoint]:
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    points: list[SwingPoint] = []
    for i in range(strength, len(df) - strength):
        left_h = highs[i - strength:i]
        right_h = highs[i + 1:i + strength + 1]
        left_l = lows[i - strength:i]
        right_l = lows[i + 1:i + strength + 1]
        if highs[i] > left_h.max() and highs[i] >= right_h.max():
            points.append(SwingPoint(df.index[i], float(highs[i]), i, SwingType.HIGH, True))
        if lows[i] < left_l.min() and lows[i] <= right_l.min():
            points.append(SwingPoint(df.index[i], float(lows[i]), i, SwingType.LOW, True))
    points.sort(key=lambda x: x.index)
    return points


def classify_structure(swings: Sequence[SwingPoint]) -> StructureAnalysis:
    highs = [s for s in swings if s.type is SwingType.HIGH and s.confirmed]
    lows = [s for s in swings if s.type is SwingType.LOW and s.confirmed]
    labels: list[StructureType] = []
    if len(highs) >= 2:
        labels.append(StructureType.HH if highs[-1].price > highs[-2].price else StructureType.LH)
    if len(lows) >= 2:
        labels.append(StructureType.HL if lows[-1].price > lows[-2].price else StructureType.LL)
    bullish = StructureType.HH in labels and StructureType.HL in labels
    bearish = StructureType.LH in labels and StructureType.LL in labels
    trend = Trend.BULLISH if bullish and not bearish else Trend.BEARISH if bearish and not bullish else Trend.NEUTRAL
    last_label = labels[-1] if labels else StructureType.NONE
    return StructureAnalysis(trend, last_label, tuple(swings), bullish, bearish)
