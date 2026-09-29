from __future__ import annotations

import math
import pandas as pd


def validate_ohlc(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    if df.empty:
        return ["DataFrame is empty"]
    required = {"open", "high", "low", "close"}
    missing = required.difference(df.columns)
    if missing:
        errors.append(f"Missing columns: {sorted(missing)}")
        return errors
    if df.index.has_duplicates:
        errors.append("Duplicate timestamps")
    if not df.index.is_monotonic_increasing:
        errors.append("Timestamps are not monotonic increasing")
    for col in required:
        if not pd.api.types.is_numeric_dtype(df[col]):
            errors.append(f"{col} is not numeric")
    valid = df[list(required)].map(lambda x: math.isfinite(float(x)) if pd.notna(x) else False)
    if not bool(valid.all().all()):
        errors.append("NaN or non-finite OHLC values")
    if bool((df["high"] < df[["open", "close", "low"]].max(axis=1)).any()):
        errors.append("Invalid high values")
    if bool((df["low"] > df[["open", "close", "high"]].min(axis=1)).any()):
        errors.append("Invalid low values")
    return errors
