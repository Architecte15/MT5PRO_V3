from __future__ import annotations

from dataclasses import dataclass

from app.utils.enums import Direction


@dataclass(frozen=True)
class PriceActionAnalysis:
    direction: Direction
    bullish_engulfing: bool = False
    bearish_engulfing: bool = False
    momentum_candle: bool = False
    wick_rejection: bool = False
    indecision_to_conviction: bool = False
    momentum_sequence: bool = False
    body_size: float = 0.0
    average_body: float = 0.0
    lower_wick: float = 0.0
    upper_wick: float = 0.0

    @property
    def confirmed(self) -> bool:
        return (self.direction is Direction.BUY and (self.bullish_engulfing or self.momentum_candle or self.wick_rejection or self.momentum_sequence)) or (self.direction is Direction.SELL and (self.bearish_engulfing or self.momentum_candle or self.wick_rejection or self.momentum_sequence))


def analyze_price_action(df, direction: Direction, momentum_factor: float = 1.8, wick_ratio: float = 2.0, sequence_len: int = 3) -> PriceActionAnalysis:
    if len(df) < max(5, sequence_len + 1):
        return PriceActionAnalysis(direction)
    cur, prev = df.iloc[-1], df.iloc[-2]
    body = abs(float(cur["close"]) - float(cur["open"]))
    recent_bodies = (df["close"] - df["open"]).abs().iloc[-11:-1]
    avg_body = float(recent_bodies.mean()) if len(recent_bodies) else 0.0
    bullish_engulfing = float(cur["close"]) > float(cur["open"]) and float(prev["close"]) < float(prev["open"]) and float(cur["open"]) <= float(prev["close"]) and float(cur["close"]) >= float(prev["open"])
    bearish_engulfing = float(cur["close"]) < float(cur["open"]) and float(prev["close"]) > float(prev["open"]) and float(cur["open"]) >= float(prev["close"]) and float(cur["close"]) <= float(prev["open"])
    momentum = avg_body > 0 and body >= avg_body * momentum_factor
    high = float(cur["high"]); low = float(cur["low"]); op = float(cur["open"]); cl = float(cur["close"])
    upper = high - max(op, cl)
    lower = min(op, cl) - low
    rng = max(high - low, 1e-12)
    wick_buy = lower >= max(body * wick_ratio, rng * 0.35) and cl >= low + rng * 0.60
    wick_sell = upper >= max(body * wick_ratio, rng * 0.35) and cl <= low + rng * 0.40
    wick_rejection = wick_buy if direction is Direction.BUY else wick_sell
    last = df.tail(sequence_len)
    bulls = bool((last["close"] > last["open"]).all())
    bears = bool((last["close"] < last["open"]).all())
    momentum_sequence = bulls if direction is Direction.BUY else bears
    prev_body = abs(float(prev["close"]) - float(prev["open"]))
    prev_range = max(float(prev["high"]) - float(prev["low"]), 1e-12)
    indecision = prev_body <= prev_range * 0.25
    conviction = float(cur["close"]) > float(cur["open"]) if direction is Direction.BUY else float(cur["close"]) < float(cur["open"])
    return PriceActionAnalysis(direction, bullish_engulfing, bearish_engulfing, momentum, wick_rejection, indecision and conviction, momentum_sequence, body, avg_body, lower, upper)
