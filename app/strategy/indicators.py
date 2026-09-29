from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def bollinger_bands(series: pd.Series, period: int = 20, deviation: float = 2.0) -> pd.DataFrame:
    middle = series.rolling(period, min_periods=period).mean()
    std = series.rolling(period, min_periods=period).std(ddof=0)
    upper = middle + deviation * std
    lower = middle - deviation * std
    width = (upper - lower) / middle.replace(0, np.nan)
    return pd.DataFrame({"bb_middle": middle, "bb_upper": upper, "bb_lower": lower, "bb_width": width})


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    out = out.fillna(100.0).where(avg_loss.ne(0), 100.0)
    out = out.where(avg_gain.ne(0), 0.0)
    return out.clip(0, 100)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    main = ema(series, fast) - ema(series, slow)
    signal_line = main.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = main - signal_line
    return pd.DataFrame({"macd_main": main, "macd_signal": signal_line, "macd_hist": hist})


def add_indicators(df: pd.DataFrame, cfg) -> pd.DataFrame:
    required = {"ema", "bb_middle", "bb_upper", "bb_lower", "bb_width", "rsi", "macd_main", "macd_signal", "macd_hist", "bb_squeeze"}
    if required.issubset(df.columns):
        return df.copy()
    out = df.copy()
    out["ema"] = ema(out["close"], cfg.ema_period)
    bb = bollinger_bands(out["close"], cfg.bollinger_period, cfg.bollinger_deviation)
    out = out.join(bb)
    out["rsi"] = rsi(out["close"], cfg.rsi_period)
    out = out.join(macd(out["close"], cfg.macd_fast, cfg.macd_slow, cfg.macd_signal))
    out["bb_squeeze"] = out["bb_width"] <= cfg.squeeze_threshold
    return out


def has_squeeze_before(series: pd.Series, lookback: int, threshold: float, minimum_candles: int) -> bool:
    tail = series.dropna().tail(lookback)
    if len(tail) < minimum_candles:
        return False
    run = 0
    for value in tail.iloc[::-1]:
        if value <= threshold:
            run += 1
        else:
            break
    return run >= minimum_candles
