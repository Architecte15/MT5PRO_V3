"""Liquidity zone mapping (spec section 2).

Zones are derived from confirmed swing points plus equal-high/equal-low
pairing and optional HTF frames. Every zone records when it became knowable
so downstream detectors can never look ahead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from app.data.timeframes import timeframe_delta
from app.strategy.market_structure import detect_swings
from app.utils.enums import SwingType

BUY_SIDE = "BUY_SIDE"
SELL_SIDE = "SELL_SIDE"

KIND_SWING = "SWING"
KIND_EQUAL = "EQUAL"
KIND_HTF = "HTF"


@dataclass
class LiquidityZone:
    zone_id: str
    zone_type: str                 # BUY_SIDE / SELL_SIDE
    timeframe: str
    price: float
    index: int                     # index inside its own frame
    timestamp: pd.Timestamp        # bar open time of the swing bar
    available_at: pd.Timestamp     # close time from which the zone is knowable
    kind: str                      # SWING / EQUAL / HTF
    touches: int = 1
    strength: float = 1.0          # unvalidated heuristic; kept explicit
    last_reaction: float = 0.0
    swept: bool = False
    sweep_index: int | None = None     # index inside the ENTRY frame (set by sweeps)
    sweep_time: pd.Timestamp | None = None
    sweep_distance: float = 0.0


def _strength_heuristic(touches: int, age_bars: int) -> float:
    # Placeholder weighting. NOT validated — deliberately isolated so tests can swap it.
    return touches + min(age_bars, 400) / 400.0


def map_liquidity_zones(
    df: pd.DataFrame,
    timeframe: str,
    swing_strength: int = 2,
    equal_tol: float = 0.00002,
    kind: str = KIND_SWING,
) -> list[LiquidityZone]:
    """Map buy-side (swing highs) and sell-side (swing lows) liquidity zones.

    available_at = close time of the confirming bar (swing bar index + strength),
    so a zone at bar k is invisible to any decision made before that close.
    """
    delta = timeframe_delta(timeframe)
    swings = detect_swings(df, swing_strength)
    n = len(df)
    zones: list[LiquidityZone] = []
    for s in swings:
        if s.index + swing_strength >= n:
            continue
        ztype = BUY_SIDE if s.type is SwingType.HIGH else SELL_SIDE
        reaction_idx = min(s.index + 6, n - 1)
        zones.append(LiquidityZone(
            zone_id=f"{timeframe}:{ztype}:{s.index}",
            zone_type=ztype,
            timeframe=timeframe,
            price=float(s.price),
            index=int(s.index),
            timestamp=pd.Timestamp(s.timestamp),
            available_at=pd.Timestamp(df.index[s.index + swing_strength]) + delta,
            kind=kind,
            last_reaction=abs(float(df["close"].iloc[reaction_idx]) - float(s.price)),
        ))

    # Equal highs / equal lows: consecutive same-side zones within tolerance.
    for ztype in (BUY_SIDE, SELL_SIDE):
        side = sorted([z for z in zones if z.zone_type == ztype], key=lambda z: z.index)
        group: list[LiquidityZone] = []
        for z in side:
            if group and abs(z.price - group[-1].price) <= equal_tol:
                group.append(z)
                continue
            _flush_equal_group(group)
            group = [z]
        _flush_equal_group(group)

    for z in zones:
        age = (n - 1) - z.index
        z.strength = _strength_heuristic(z.touches, age)
    return zones


def _flush_equal_group(group: list[LiquidityZone]) -> None:
    if len(group) >= 2:
        for z in group:
            z.kind = KIND_EQUAL
            z.touches = len(group)


def available_zones_at(zones: list[LiquidityZone], decision_close: pd.Timestamp) -> list[LiquidityZone]:
    """Zones knowable at a given decision close time (no lookahead)."""
    return [z for z in zones if z.available_at <= decision_close]
