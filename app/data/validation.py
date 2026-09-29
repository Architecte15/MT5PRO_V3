from __future__ import annotations

import pandas as pd


def validate_market_frame(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        errors.append(f"Missing OHLC columns: {sorted(missing)}")
        return errors
    if df.empty:
        return ["DataFrame is empty"]
    if not isinstance(df.index, pd.DatetimeIndex):
        errors.append("Index must be a DatetimeIndex")
    if df.index.has_duplicates:
        errors.append("Duplicate timestamps")
    if not df.index.is_monotonic_increasing:
        errors.append("Timestamps are not monotonic increasing")
    if df[list(required)].isna().any().any():
        errors.append("NaN in OHLC")
    if (df["high"] < df[["open", "close", "low"]].max(axis=1)).any():
        errors.append("Invalid high values")
    if (df["low"] > df[["open", "close", "high"]].min(axis=1)).any():
        errors.append("Invalid low values")
    return errors
