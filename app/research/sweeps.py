"""Liquidity sweep detection (spec section 3).

A sweep is not merely "price exceeded an old high": each event records the
piercing context (distance, candle anatomy, ATR-relative size, volume,
reintegration, pre-sweep trend and momentum). Weak vs confirmed classification
depends on whether price closes back inside the zone within reentry_max_bars.
Displacement is measured separately (displacement.py) and kept as an
independent component (spec section 8).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.data.timeframes import timeframe_delta
from app.research.structure import trend_at
from app.research.zones import BUY_SIDE, SELL_SIDE, LiquidityZone
from app.strategy.market_structure import detect_swings

SWEEP_WEAK = "WEAK"
SWEEP_CONFIRMED = "CONFIRMED"


@dataclass
class SweepEvent:
    index: int                          # piercing bar (entry frame)
    timestamp: pd.Timestamp
    decision_close: pd.Timestamp        # time at which the sweep becomes observable
    zone_id: str
    zone_type: str
    zone_timeframe: str
    level: float
    pierce_distance: float
    candle_range: float
    body: float
    upper_wick: float
    lower_wick: float
    atr_rel: float
    volume: float
    volume_rel: float
    closed_back: bool
    reentry_bars: int                   # bars after pierce until close back inside; -1 = never
    sweep_class: str                    # WEAK / CONFIRMED
    trend_before: str
    momentum_before: float
    zone_age_bars: int
    displacement: str = "NO_DISPLACEMENT"     # filled later — independent component
    displacement_metrics: dict = field(default_factory=dict)


def detect_sweeps(
    df: pd.DataFrame,
    zones: list[LiquidityZone],
    atr: pd.Series,
    swing_strength: int = 2,
    reentry_max_bars: int = 3,
    momentum_lookback: int = 10,
    warmup: int = 30,
) -> list[SweepEvent]:
    entry_delta = timeframe_delta("M15")
    decision_close = pd.DatetimeIndex(df.index) + entry_delta
    opens = df["open"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    volumes = df["volume"].to_numpy(dtype=float) if "volume" in df.columns else np.zeros(len(df))
    atr_arr = atr.to_numpy(dtype=float)
    vol_med = pd.Series(volumes).rolling(50, min_periods=10).median().to_numpy()
    swings = detect_swings(df, swing_strength)
    events: list[SweepEvent] = []
    seen: dict[tuple[str, int], list[float]] = {}
    equal_tol = 0.00002

    for zone in zones:
        available_mask = decision_close >= zone.available_at
        if zone.zone_type == BUY_SIDE:
            pierced = highs > zone.price
        else:
            pierced = lows < zone.price
        candidates = np.flatnonzero(pierced & available_mask)
        candidates = candidates[candidates >= warmup]
        if candidates.size == 0:
            continue
        i0 = int(candidates[0])

        # Equal zones (and H4/M15 twins) pierce together: keep one physical event
        # per side/bar/price-cluster (within equal_tol).
        key = (zone.zone_type, i0)
        if key in seen and any(abs(zone.price - p) <= equal_tol for p in seen[key]):
            continue
        seen.setdefault(key, []).append(zone.price)

        if zone.zone_type == BUY_SIDE:
            closed_back = bool(closes[i0] < zone.price)
            pierce = highs[i0] - zone.price
            wick_up = highs[i0] - max(opens[i0], closes[i0])
            wick_dn = min(opens[i0], closes[i0]) - lows[i0]
            reentry = _first_reentry(closes, i0, zone.price, reentry_max_bars, above=False)
        else:
            closed_back = bool(closes[i0] > zone.price)
            pierce = zone.price - lows[i0]
            wick_up = highs[i0] - max(opens[i0], closes[i0])
            wick_dn = min(opens[i0], closes[i0]) - lows[i0]
            reentry = _first_reentry(closes, i0, zone.price, reentry_max_bars, above=True)

        confirmed = closed_back or reentry > 0
        sweep_class = SWEEP_CONFIRMED if confirmed else SWEEP_WEAK
        atr_v = float(atr_arr[i0])
        mom_idx = max(i0 - momentum_lookback, 0)

        ev = SweepEvent(
            index=i0,
            timestamp=pd.Timestamp(df.index[i0]),
            decision_close=pd.Timestamp(decision_close[i0]),
            zone_id=zone.zone_id,
            zone_type=zone.zone_type,
            zone_timeframe=zone.timeframe,
            level=zone.price,
            pierce_distance=float(pierce),
            candle_range=float(highs[i0] - lows[i0]),
            body=float(abs(closes[i0] - opens[i0])),
            upper_wick=float(wick_up),
            lower_wick=float(wick_dn),
            atr_rel=float((highs[i0] - lows[i0]) / atr_v) if atr_v > 0 else 0.0,
            volume=float(volumes[i0]),
            volume_rel=float(volumes[i0] / vol_med[i0]) if vol_med[i0] else 0.0,
            closed_back=closed_back,
            reentry_bars=int(reentry),
            sweep_class=sweep_class,
            trend_before=trend_at(swings, i0, swing_strength),
            momentum_before=float(closes[i0] - closes[mom_idx]),
            # age in entry-TF bars since the zone's own swing candle closed
            zone_age_bars=int(
                (decision_close[i0] - (zone.timestamp + timeframe_delta(zone.timeframe)))
                / entry_delta
            ),
        )
        events.append(ev)

        zone.swept = True
        zone.sweep_index = i0
        zone.sweep_time = pd.Timestamp(df.index[i0])
        zone.sweep_distance = float(pierce)

    events.sort(key=lambda e: e.index)
    return events


def _first_reentry(closes: np.ndarray, i0: int, level: float, max_bars: int, above: bool) -> int:
    """Bars after the pierce until a close returns inside the zone; -1 if none."""
    end = min(i0 + max_bars, len(closes) - 1)
    for j in range(i0 + 1, end + 1):
        if (closes[j] < level) if not above else (closes[j] > level):
            return j - i0
    return -1
