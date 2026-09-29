from __future__ import annotations

import numpy as np
import pandas as pd


def make_ohlc(n=300, start=100.0, drift=0.03, noise=0.15, seed=42):
    rng = np.random.default_rng(seed)
    returns = drift + rng.normal(0, noise, n)
    close = start + np.cumsum(returns)
    open_ = np.r_[start, close[:-1]]
    spread = np.abs(rng.normal(0.15, 0.05, n))
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    idx = pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": 1000}, index=idx)
