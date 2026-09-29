"""Unit tests: liquidity zone mapping (spec section 2)."""

import numpy as np
import pandas as pd

from app.research.zones import (
    BUY_SIDE,
    KIND_EQUAL,
    SELL_SIDE,
    map_liquidity_zones,
)


def make_frame(closes, highs=None, lows=None, start="2026-01-05 00:00"):
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


def _spike_frame(n=60):
    closes = np.full(n, 1.1000)
    highs = np.full(n, 1.1002)
    lows = np.full(n, 1.0998)
    highs[5] = 1.1050                       # swing high
    lows[20] = 1.0950                        # swing low
    highs[40] = highs[50] = 1.1080           # equal highs
    return make_frame(closes, highs, lows)


def test_zones_map_both_sides_from_swings():
    df = _spike_frame()
    zones = map_liquidity_zones(df, "M15")
    buy = {round(z.price, 5) for z in zones if z.zone_type == BUY_SIDE}
    sell = {round(z.price, 5) for z in zones if z.zone_type == SELL_SIDE}
    assert 1.1050 in buy
    assert 1.0950 in sell
    # only crafted spikes are swings (flat frames produce no strict swings)
    assert buy <= {1.1050, 1.1080}


def test_available_at_is_confirming_bar_close():
    df = _spike_frame()
    zones = map_liquidity_zones(df, "M15")
    z = next(z for z in zones if abs(z.price - 1.1050) < 1e-9)
    # swing at index 5, strength 2 -> knowable at close of bar 7
    assert z.index == 5
    assert z.available_at == df.index[7] + pd.Timedelta(minutes=15)


def test_equal_highs_grouped_with_touches():
    df = _spike_frame()
    zones = map_liquidity_zones(df, "M15")
    equals = [z for z in zones if z.kind == KIND_EQUAL]
    assert len(equals) == 2
    assert all(z.touches == 2 for z in equals)
    assert all(abs(z.price - 1.1080) < 1e-9 for z in equals)
