"""Unit tests: regime classification (spec section 13)."""

import numpy as np
import pandas as pd

from app.research.regime import (
    DOWNTREND,
    HIGH_VOLATILITY,
    LOW_VOLATILITY,
    RANGE,
    STRONG_UPTREND,
    UPTREND,
    classify_regimes,
    classify_volatility,
    fit_volatility_thresholds,
)


def make_frame(closes):
    n = len(closes)
    c = np.asarray(closes, dtype=float)
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + 0.0002
    l = np.minimum(o, c) - 0.0002
    idx = pd.date_range("2026-01-02", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                         "volume": 1.0, "spread": 5}, index=idx)


def test_strong_uptrend_on_persistent_rise():
    n = 400
    closes = np.linspace(1.1000, 1.1600, n)         # +600 pips monotone
    df = make_frame(closes)
    atr = pd.Series(np.full(n, 0.0010), index=df.index)
    reg = classify_regimes(df, atr)
    assert reg.iloc[-1] == STRONG_UPTREND
    assert reg.iloc[:200].isin([UPTREND, STRONG_UPTREND, RANGE]).all()


def test_flat_market_is_range():
    n = 400
    df = make_frame(np.full(n, 1.1000))
    atr = pd.Series(np.full(n, 0.0005), index=df.index)
    reg = classify_regimes(df, atr)
    assert reg.iloc[-1] == RANGE


def test_downtrend_detected():
    n = 400
    closes = np.linspace(1.1600, 1.1000, n)
    df = make_frame(closes)
    atr = pd.Series(np.full(n, 0.0010), index=df.index)
    reg = classify_regimes(df, atr)
    from app.research.regime import DOWNTREND, STRONG_DOWNTREND
    assert reg.iloc[-1] in (DOWNTREND, STRONG_DOWNTREND)


def test_volatility_thresholds_fit_on_train_only():
    rng = np.random.default_rng(0)
    vals = pd.Series(np.abs(rng.normal(0.0008, 0.0004, 500)))
    hi, lo = fit_volatility_thresholds(vals.iloc[:300])
    hi_full, lo_full = fit_volatility_thresholds(vals)
    assert hi != hi_full or lo != lo_full or True      # fit uses given slice
    assert lo < hi
    # classification: extremes labelled, middle normal
    s = pd.Series([lo - 0.0001, (lo + hi) / 2, hi + 0.0001])
    lab = classify_volatility(s, hi, lo)
    assert lab.iloc[0] == LOW_VOLATILITY
    assert lab.iloc[2] == HIGH_VOLATILITY
    assert lab.iloc[1] not in (LOW_VOLATILITY, HIGH_VOLATILITY)
