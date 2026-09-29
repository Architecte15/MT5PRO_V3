from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

from app.strategy.market_structure import SwingPoint, detect_swings, classify_structure
from app.strategy.indicators import add_indicators
from app.config.models import IndicatorConfig
from app.utils.enums import Direction, SwingType


class LiquidityType(str, Enum):
    BUY_SIDE = "BUY_SIDE"
    SELL_SIDE = "SELL_SIDE"


class DisplacementStrength(str, Enum):
    NO_DISPLACEMENT = "NO_DISPLACEMENT"
    WEAK_DISPLACEMENT = "WEAK_DISPLACEMENT"
    MODERATE_DISPLACEMENT = "MODERATE_DISPLACEMENT"
    STRONG_DISPLACEMENT = "STRONG_DISPLACEMENT"


@dataclass(frozen=True)
class LiquidityZone:
    zone_id: str
    type: LiquidityType
    timeframe: str
    price: float
    distance_from_price: float
    age: int
    number_of_touches: int
    strength: float
    last_reaction: float
    swept: bool = False
    sweep_time: pd.Timestamp | None = None


@dataclass(frozen=True)
class SweepEvent:
    zone_id: str
    direction: Direction
    level: float
    overshoot: float
    candle_range: float
    body: float
    upper_wick: float
    lower_wick: float
    atr: float
    atr_relative_range: float
    close_reclaimed: bool
    confirmed: bool
    timestamp: pd.Timestamp


@dataclass(frozen=True)
class DisplacementEvent:
    direction: Direction
    strength: DisplacementStrength
    body_atr: float
    range_atr: float
    consecutive_directional_candles: int
    distance_from_sweep: float
    timestamp: pd.Timestamp


@dataclass(frozen=True)
class LiquidityFlowFeatures:
    timestamp: pd.Timestamp
    nearest_buy_liquidity: float | None
    nearest_sell_liquidity: float | None
    liquidity_swept: bool
    sweep_direction: Direction
    sweep_strength: str
    displacement_strength: str
    bos: bool
    choch: bool
    ema13_confirmation: bool
    regime: str
    session: str
    feature_version: str = "LF-1.0"

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["sweep_direction"] = self.sweep_direction.value
        return out


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def _touch_count(df: pd.DataFrame, level: float, tolerance: float, upto: int) -> int:
    sample = df.iloc[:upto]
    return int(((sample["high"] - level).abs() <= tolerance).sum() + ((sample["low"] - level).abs() <= tolerance).sum())


def detect_liquidity_zones(df: pd.DataFrame, timeframe: str, swing_strength: int = 2, tolerance: float = 0.00015, max_zones: int = 100) -> list[LiquidityZone]:
    if len(df) < swing_strength * 2 + 5:
        return []
    swings = detect_swings(df, swing_strength)
    last_price = float(df.iloc[-1]["close"])
    zones: list[LiquidityZone] = []
    for n, swing in enumerate(swings[-max_zones:]):
        ztype = LiquidityType.BUY_SIDE if swing.type is SwingType.HIGH else LiquidityType.SELL_SIDE
        touches = _touch_count(df, swing.price, tolerance, len(df))
        age = max(0, len(df) - 1 - swing.index)
        reaction = abs(float(df.iloc[min(swing.index + 1, len(df)-1)]["close"]) - swing.price)
        strength = float(np.clip(1.0 + 0.25 * touches + reaction / max(tolerance, 1e-12), 0.0, 10.0))
        zones.append(LiquidityZone(f"{timeframe}-{swing.index}-{swing.type.value}", ztype, timeframe, swing.price,
                                   abs(last_price - swing.price), age, touches, strength, reaction))
    return zones


def detect_sweep(df: pd.DataFrame, zones: list[LiquidityZone], atr_period: int = 14, tolerance: float = 0.00005) -> SweepEvent | None:
    if len(df) < atr_period + 2 or not zones:
        return None
    row = df.iloc[-1]
    atr = float(_atr(df, atr_period).iloc[-1])
    if not np.isfinite(atr) or atr <= 0:
        return None
    candidates: list[tuple[float, SweepEvent]] = []
    candle_range = float(row.high - row.low)
    body = abs(float(row.close - row.open))
    upper = float(row.high - max(row.open, row.close))
    lower = float(min(row.open, row.close) - row.low)
    for z in zones:
        if z.type is LiquidityType.SELL_SIDE and float(row.low) < z.price - tolerance:
            reclaimed = float(row.close) > z.price
            overshoot = z.price - float(row.low)
            ev = SweepEvent(z.zone_id, Direction.BUY, z.price, overshoot, candle_range, body, upper, lower, atr,
                            candle_range / atr, reclaimed, reclaimed, pd.Timestamp(df.index[-1]))
        elif z.type is LiquidityType.BUY_SIDE and float(row.high) > z.price + tolerance:
            reclaimed = float(row.close) < z.price
            overshoot = float(row.high) - z.price
            ev = SweepEvent(z.zone_id, Direction.SELL, z.price, overshoot, candle_range, body, upper, lower, atr,
                            candle_range / atr, reclaimed, reclaimed, pd.Timestamp(df.index[-1]))
        else:
            continue
        strength = (2.0 if ev.confirmed else 0.5) + min(3.0, ev.atr_relative_range) + min(2.0, ev.overshoot / atr)
        candidates.append((strength, ev))
    return max(candidates, key=lambda x: x[0])[1] if candidates else None


def measure_displacement(df: pd.DataFrame, sweep: SweepEvent | None, atr_period: int = 14,
                         weak_body_atr: float = 0.5, moderate_body_atr: float = 1.0,
                         strong_body_atr: float = 1.5) -> DisplacementEvent | None:
    if sweep is None or len(df) < atr_period + 3:
        return None
    atr = float(_atr(df, atr_period).iloc[-1])
    if not np.isfinite(atr) or atr <= 0:
        return None
    recent = df.iloc[-3:]
    directional = []
    for _, r in recent.iterrows():
        sign = 1 if r.close > r.open else -1 if r.close < r.open else 0
        directional.append(sign == sweep.direction.sign)
    consecutive = 0
    for ok in reversed(directional):
        if ok: consecutive += 1
        else: break
    last = df.iloc[-1]
    body_atr = abs(float(last.close - last.open)) / atr
    range_atr = float(last.high - last.low) / atr
    if body_atr >= strong_body_atr and consecutive >= 2:
        strength = DisplacementStrength.STRONG_DISPLACEMENT
    elif body_atr >= moderate_body_atr and consecutive >= 1:
        strength = DisplacementStrength.MODERATE_DISPLACEMENT
    elif body_atr >= weak_body_atr:
        strength = DisplacementStrength.WEAK_DISPLACEMENT
    else:
        strength = DisplacementStrength.NO_DISPLACEMENT
    return DisplacementEvent(sweep.direction, strength, body_atr, range_atr, consecutive,
                             abs(float(last.close) - sweep.level), pd.Timestamp(df.index[-1]))


def structure_break_after_sweep(df: pd.DataFrame, sweep: SweepEvent | None, swing_strength: int = 2) -> tuple[bool, bool]:
    if sweep is None or len(df) < swing_strength * 2 + 5:
        return False, False
    swings = detect_swings(df, swing_strength)
    if len(swings) < 4:
        return False, False
    prior = [s for s in swings if s.timestamp < sweep.timestamp]
    if len(prior) < 2:
        return False, False
    highs = [s.price for s in prior if s.type is SwingType.HIGH]
    lows = [s.price for s in prior if s.type is SwingType.LOW]
    close = float(df.iloc[-1].close)
    if sweep.direction is Direction.BUY and highs:
        bos = close > max(highs[-2:])
        choch = bos and len(lows) >= 2 and lows[-1] <= lows[-2]
    elif sweep.direction is Direction.SELL and lows:
        bos = close < min(lows[-2:])
        choch = bos and len(highs) >= 2 and highs[-1] >= highs[-2]
    else:
        return False, False
    return bool(bos), bool(choch)


def regime_label(df: pd.DataFrame, ema_period: int = 50) -> str:
    if len(df) < ema_period + 5:
        return "UNKNOWN"
    close = df["close"].astype(float)
    ema = close.ewm(span=ema_period, adjust=False).mean()
    slope = float(ema.iloc[-1] - ema.iloc[-5])
    atr = _atr(df, 14)
    rel_vol = float(atr.iloc[-1] / close.iloc[-1]) if close.iloc[-1] else 0.0
    if rel_vol > 0.003:
        return "HIGH_VOLATILITY"
    if rel_vol < 0.0008:
        return "LOW_VOLATILITY"
    if close.iloc[-1] > ema.iloc[-1] and slope > 0:
        return "STRONG_UPTREND" if slope > close.iloc[-1] * 0.001 else "UPTREND"
    if close.iloc[-1] < ema.iloc[-1] and slope < 0:
        return "STRONG_DOWNTREND" if abs(slope) > close.iloc[-1] * 0.001 else "DOWNTREND"
    return "RANGE"


def session_label(ts: pd.Timestamp) -> str:
    h = ts.hour
    if 0 <= h < 7: return "ASIA"
    if 7 <= h < 13: return "LONDON"
    if 13 <= h < 17: return "OVERLAP"
    if 17 <= h < 22: return "NEW_YORK"
    return "OFF_SESSION"


def build_features(df: pd.DataFrame, timeframe: str, indicator_config: IndicatorConfig, swing_strength: int = 2,
                   tolerance: float = 0.00015) -> tuple[LiquidityFlowFeatures, list[LiquidityZone], SweepEvent | None, DisplacementEvent | None]:
    enriched = add_indicators(df, indicator_config)
    zones = detect_liquidity_zones(enriched, timeframe, swing_strength, tolerance)
    sweep = detect_sweep(enriched, zones, indicator_config.rsi_period, tolerance / 3)
    displacement = measure_displacement(enriched, sweep)
    bos, choch = structure_break_after_sweep(enriched, sweep, swing_strength)
    ema13 = enriched["close"].ewm(span=13, adjust=False).mean()
    if sweep is None:
        ema_confirm = False
    else:
        ema_confirm = bool(enriched.iloc[-1].close > ema13.iloc[-1]) if sweep.direction is Direction.BUY else bool(enriched.iloc[-1].close < ema13.iloc[-1])
    buy = [z.price for z in zones if z.type is LiquidityType.BUY_SIDE and z.price >= float(enriched.iloc[-1].close)]
    sell = [z.price for z in zones if z.type is LiquidityType.SELL_SIDE and z.price <= float(enriched.iloc[-1].close)]
    ts = pd.Timestamp(enriched.index[-1])
    features = LiquidityFlowFeatures(ts, min(buy, default=None), max(sell, default=None), sweep is not None,
        sweep.direction if sweep else Direction.FLAT, "CONFIRMED" if sweep and sweep.confirmed else "NONE",
        displacement.strength.value if displacement else DisplacementStrength.NO_DISPLACEMENT.value,
        bos, choch, ema_confirm, regime_label(enriched), session_label(ts))
    return features, zones, sweep, displacement
