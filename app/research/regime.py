"""Market regime classification (spec section 13).

Trend regimes come from EMA200 slope relative to ATR (parameters, pre-registered).
Volatility buckets are fit on the TRAIN period only to avoid leaking the future
distribution into regime labels of earlier bars.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.strategy.indicators import ema

STRONG_UPTREND = "STRONG_UPTREND"
UPTREND = "UPTREND"
RANGE = "RANGE"
DOWNTREND = "DOWNTREND"
STRONG_DOWNTREND = "STRONG_DOWNTREND"

HIGH_VOLATILITY = "HIGH_VOLATILITY"
LOW_VOLATILITY = "LOW_VOLATILITY"
NORMAL_VOLATILITY = "NORMAL_VOLATILITY"


@dataclass(frozen=True)
class RegimeParams:
    ema_period: int = 200
    slope_bars: int = 20
    weak_slope_atr: float = 0.10    # slope over slope_bars, expressed in ATR units
    strong_slope_atr: float = 0.35


def classify_regimes(df: pd.DataFrame, atr: pd.Series, params: RegimeParams = RegimeParams()) -> pd.Series:
    e = ema(df["close"], params.ema_period)
    slope = (e - e.shift(params.slope_bars)) / atr.replace(0, np.nan)
    close = df["close"]
    out = pd.Series(RANGE, index=df.index, dtype=object)
    above = close > e
    below = close < e
    out[above & (slope > params.weak_slope_atr)] = UPTREND
    out[above & (slope > params.strong_slope_atr)] = STRONG_UPTREND
    out[below & (slope < -params.weak_slope_atr)] = DOWNTREND
    out[below & (slope < -params.strong_slope_atr)] = STRONG_DOWNTREND
    out[slope.isna()] = RANGE
    return out


def fit_volatility_thresholds(atr_pct_train: pd.Series, hi_q: float = 0.75, lo_q: float = 0.25) -> tuple[float, float]:
    clean = atr_pct_train.dropna()
    return float(clean.quantile(hi_q)), float(clean.quantile(lo_q))


def classify_volatility(atr_pct: pd.Series, hi: float, lo: float) -> pd.Series:
    out = pd.Series(NORMAL_VOLATILITY, index=atr_pct.index, dtype=object)
    out[atr_pct > hi] = HIGH_VOLATILITY
    out[atr_pct < lo] = LOW_VOLATILITY
    return out
