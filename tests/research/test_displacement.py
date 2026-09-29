"""Unit tests: displacement classification (spec section 4).

Thresholds are pre-registered parameters — tests pin the ordering semantics
and that direction/ATR normalization behave as declared.
"""

import numpy as np
import pandas as pd

from app.research.displacement import (
    MODERATE_DISPLACEMENT,
    NO_DISPLACEMENT,
    STRONG_DISPLACEMENT,
    WEAK_DISPLACEMENT,
    DisplacementParams,
    measure_displacement,
)


def make_frame(closes, start="2026-07-06 00:00"):
    n = len(closes)
    c = np.asarray(closes, dtype=float)
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c)
    l = np.minimum(o, c)
    idx = pd.date_range(start, periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                         "volume": 1.0, "spread": 5}, index=idx)


def atr_const(n, v=0.0010):
    return np.full(n, v)


def test_strong_bullish_impulse_after_sell_side_sweep():
    # sweep at index 3, then 3 directional candles running +2.0 ATR total
    closes = [1.1000, 1.1000, 1.1000, 1.1000, 1.1008, 1.1014, 1.1020, 1.1021]
    df = make_frame(closes)
    label, m = measure_displacement(df, atr_const(len(df)), 3, +1)
    assert label == STRONG_DISPLACEMENT
    assert m["run_atr"] >= 1.6
    assert m["dir_candles"] >= 2


def test_moderate_threshold_respected():
    # run = c[6]-c[3] = 1.10105-1.1000 = 1.05 ATR -> strictly between 1.0 and 1.6
    closes = [1.1000, 1.1000, 1.1000, 1.1000, 1.1004, 1.1007, 1.10105, 1.1012]
    df = make_frame(closes)
    label, m = measure_displacement(df, atr_const(len(df)), 3, +1)
    assert label == MODERATE_DISPLACEMENT
    assert 1.0 <= m["run_atr"] < 1.6


def test_no_impulse_below_weak_threshold():
    closes = [1.1000, 1.1000, 1.1000, 1.1000, 1.1001, 1.1002, 1.1004, 1.1004]
    df = make_frame(closes)
    label, _ = measure_displacement(df, atr_const(len(df)), 3, +1)
    assert label == NO_DISPLACEMENT


def test_wrong_direction_is_no_displacement():
    closes = [1.1000, 1.1000, 1.1000, 1.1000, 1.1008, 1.1014, 1.1020, 1.1021]
    df = make_frame(closes)
    label, _ = measure_displacement(df, atr_const(len(df)), 3, -1)   # bearish expected
    assert label == NO_DISPLACEMENT


def test_weak_category_between_thresholds():
    params = DisplacementParams(weak_atr=0.6, moderate_atr=1.0, strong_atr=1.6)
    closes = [1.1000, 1.1000, 1.1000, 1.1000, 1.1003, 1.1005, 1.1007, 1.1007]
    df = make_frame(closes)
    label, m = measure_displacement(df, atr_const(len(df)), 3, +1, params)
    assert label == WEAK_DISPLACEMENT
    assert 0.6 <= m["run_atr"] < 1.0


def test_sweep_at_series_tail_yields_no_displacement():
    closes = [1.1000, 1.1001, 1.1002, 1.1003]
    df = make_frame(closes)
    label, m = measure_displacement(df, atr_const(len(df)), 3, +1)
    assert label == NO_DISPLACEMENT
    assert m["run_atr"] == 0.0
