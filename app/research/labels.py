"""Outcome labels (spec section 11, second half) — FUTURE data, evaluation only.

Nothing in this module may be used as a feature for an entry decision; the
research runner joins labels solely to score hypotheses after the fact.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def forward_labels(df: pd.DataFrame, horizon: int = 96) -> pd.DataFrame:
    """Per-bar forward outcomes over `horizon` bars (long orientation).

    future_return: close[i+horizon] - close[i]
    mfe_long: max high of (i+1..i+horizon) - close[i]
    mae_long: close[i] - min low of (i+1..i+horizon)
    """
    n = len(df)
    closes = df["close"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    fut_ret = np.full(n, np.nan)
    mfe = np.full(n, np.nan)
    mae = np.full(n, np.nan)
    for i in range(n - horizon):
        j = i + horizon
        fut_ret[i] = closes[j] - closes[i]
        mfe[i] = highs[i + 1:j + 1].max() - closes[i]
        mae[i] = closes[i] - lows[i + 1:j + 1].min()
    return pd.DataFrame(
        {"future_return": fut_ret, "mfe_long": mfe, "mae_long": mae},
        index=df.index,
    )
