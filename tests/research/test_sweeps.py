"""Unit tests: liquidity sweep detection (spec section 3).

Key invariant: a zone is only eligible from its available_at close, and equal
zones piercing together collapse into a single physical event.
"""

import numpy as np
import pandas as pd

from app.research.sweeps import SWEEP_CONFIRMED, SWEEP_WEAK, detect_sweeps
from app.research.zones import BUY_SIDE, KIND_SWING, LiquidityZone


def make_frame(closes, highs=None, lows=None, start="2026-03-02 00:00"):
    n = len(closes)
    idx = pd.date_range(start, periods=n, freq="15min", tz="UTC")
    c = np.asarray(closes, dtype=float)
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + 0.0002 if highs is None else np.asarray(highs, dtype=float)
    l = np.minimum(o, c) - 0.0003 if lows is None else np.asarray(lows, dtype=float)
    return pd.DataFrame(
        {"open": o, "high": h, "low": l, "close": c, "volume": 100.0, "spread": 10},
        index=idx,
    )


def buy_zone(df, price=1.1010, index=5) -> LiquidityZone:
    return LiquidityZone(
        zone_id=f"M15:{BUY_SIDE}:{index}", zone_type=BUY_SIDE, timeframe="M15",
        price=price, index=index, timestamp=pd.Timestamp(df.index[index]),
        available_at=pd.Timestamp(df.index[index + 2]) + pd.Timedelta(minutes=15),
        kind=KIND_SWING,
    )


def atr_of(df, value=0.0010) -> pd.Series:
    return pd.Series(np.full(len(df), value), index=df.index)


def test_pierce_before_availability_is_ignored_confirmed_at_first_valid():
    n = 60
    closes = np.full(n, 1.1000)
    highs = np.full(n, 1.1002)
    highs[6] = 1.1012          # pierce BEFORE zone availability (bar 7 close) -> ignored
    closes[32] = 1.1008        # pierce + close back inside at 32 -> confirmed
    highs[32] = 1.1015
    df = make_frame(closes, highs)
    events = detect_sweeps(df, [buy_zone(df)], atr_of(df))
    assert len(events) == 1
    ev = events[0]
    assert ev.index == 32
    assert ev.sweep_class == SWEEP_CONFIRMED
    assert ev.closed_back is True
    assert abs(ev.pierce_distance - 0.0005) < 1e-12


def test_pierce_without_reintegration_is_weak():
    n = 60
    closes = np.full(n, 1.1000)
    highs = np.full(n, 1.1002)
    highs[32] = 1.1015
    closes[32] = 1.1012         # close beyond the level
    closes[33:36] = 1.1011      # stays beyond for the whole reentry window
    df = make_frame(closes, highs)
    events = detect_sweeps(df, [buy_zone(df)], atr_of(df))
    assert len(events) == 1
    ev = events[0]
    assert ev.index == 32
    assert ev.sweep_class == SWEEP_WEAK
    assert ev.closed_back is False
    assert ev.reentry_bars == -1


def test_equal_zones_pierce_produces_single_event():
    n = 60
    closes = np.full(n, 1.1000)
    highs = np.full(n, 1.1002)
    highs[32] = 1.1015
    closes[32] = 1.1008
    df = make_frame(closes, highs)
    z1 = buy_zone(df, price=1.1010)
    z2 = buy_zone(df, price=1.10100 + 0.00001)   # 1 point apart -> same physical level
    events = detect_sweeps(df, [z1, z2], atr_of(df))
    assert len(events) == 1


def test_zone_marked_swept_with_context_fields():
    n = 60
    closes = np.full(n, 1.1000)
    highs = np.full(n, 1.1002)
    highs[32] = 1.1015
    closes[32] = 1.1008
    df = make_frame(closes, highs)
    zone = buy_zone(df)
    events = detect_sweeps(df, [zone], atr_of(df, value=0.0012))
    assert zone.swept is True
    assert zone.sweep_index == events[0].index
    ev = events[0]
    assert ev.atr_rel > 0                      # candle range / ATR
    assert ev.volume_rel > 0                   # vs rolling median volume
    assert ev.zone_age_bars == 32 - 5
    assert ev.trend_before in {"BULLISH", "BEARISH", "NEUTRAL"}
    # close[32]=1.1008 minus close[22]=1.1000 (momentum lookback 10)
    assert abs(ev.momentum_before - 0.0008) < 1e-9
