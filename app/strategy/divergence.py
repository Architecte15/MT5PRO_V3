from __future__ import annotations

from dataclasses import dataclass

from app.strategy.market_structure import SwingPoint
from app.utils.enums import Direction, SwingType


@dataclass(frozen=True)
class DivergenceAnalysis:
    bullish: bool = False
    bearish: bool = False
    price_points: tuple[float, float] | None = None
    indicator_points: tuple[float, float] | None = None


def rsi_divergence(df, swings: list[SwingPoint], lookback: int = 30) -> DivergenceAnalysis:
    confirmed = [s for s in swings if s.confirmed and s.index >= max(0, len(df) - lookback)]
    lows = [s for s in confirmed if s.type is SwingType.LOW]
    highs = [s for s in confirmed if s.type is SwingType.HIGH]
    bullish = bearish = False
    bp = ip = None
    if len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        ra, rb = float(df["rsi"].iloc[a.index]), float(df["rsi"].iloc[b.index])
        bullish = b.price < a.price and rb > ra
        if bullish: bp, ip = (a.price, b.price), (ra, rb)
    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        ra, rb = float(df["rsi"].iloc[a.index]), float(df["rsi"].iloc[b.index])
        bearish = b.price > a.price and rb < ra
        if bearish: bp, ip = (a.price, b.price), (ra, rb)
    return DivergenceAnalysis(bullish, bearish, bp, ip)
