from __future__ import annotations

import numpy as np
import pandas as pd

FEATURES = ["sweep", "bos", "ema13_confirmation", "future_return", "mfe", "mae"]


def nearest_historical_setups(dataset: pd.DataFrame, query: pd.Series, k: int = 10, before: pd.Timestamp | None = None) -> pd.DataFrame:
    """Causal similarity search: rows at/after `before` are excluded from historical memory."""
    d = dataset.copy()
    if before is not None and "timestamp" in d:
        d = d[pd.to_datetime(d["timestamp"]) < pd.Timestamp(before)]
    cols = [c for c in FEATURES if c in d and c in query.index]
    if not cols or d.empty: return d.iloc[0:0]
    X = d[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(dtype=float)
    q = pd.to_numeric(query[cols], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    scale = np.nanstd(X, axis=0); scale[scale == 0] = 1.0
    dist = np.sqrt(((X-q)/scale).astype(float).__pow__(2).sum(axis=1))
    d = d.assign(_distance=dist).sort_values("_distance").head(k)
    return d
