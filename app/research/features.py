"""Per-candle observation features (spec section 11).

Everything here is computable at the close of the bar itself: rolling stats
are shifted where they must not include the current bar, and nothing ever
reads beyond index i. Outcome labels live in labels.py and must never be
joined into anything used for entry decisions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.strategy.indicators import ema, macd, rsi


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr = true_range(df)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def bar_features(
    df: pd.DataFrame,
    atr_period: int = 14,
    ema13_period: int = 13,
    ema200_period: int = 200,
    rsi_period: int = 14,
    momentum_lookback: int = 10,
) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    out["range"] = h - l
    out["body"] = c - o
    out["upper_wick"] = h - pd.concat([o, c], axis=1).max(axis=1)
    out["lower_wick"] = pd.concat([o, c], axis=1).min(axis=1) - l
    out["atr"] = atr(df, atr_period)
    out["atr_pct"] = out["atr"] / c
    out["rsi"] = rsi(c, rsi_period)
    out["ema13"] = ema(c, ema13_period)
    out["ema200"] = ema(c, ema200_period)
    out["ema13_slope"] = out["ema13"] - out["ema13"].shift(5)
    out["macd_hist"] = macd(c)["macd_hist"]
    out["momentum"] = c - c.shift(momentum_lookback)
    out["rolling_high_20"] = h.shift(1).rolling(20, min_periods=5).max()
    out["rolling_low_20"] = l.shift(1).rolling(20, min_periods=5).min()
    out["volume"] = df["volume"] if "volume" in df.columns else 0.0
    out["spread"] = df["spread"] if "spread" in df.columns else 0.0
    out["hour"] = pd.DatetimeIndex(df.index).hour
    out["weekday"] = pd.DatetimeIndex(df.index).weekday
    return out
