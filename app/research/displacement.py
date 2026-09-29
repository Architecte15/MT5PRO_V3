"""Displacement / impulse measurement (spec section 4).

Thresholds are parameters, never silently hardcoded as "the truth": the
research runner grids them on TRAIN only and freezes the selection before
touching validation/OOS/holdout.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

NO_DISPLACEMENT = "NO_DISPLACEMENT"
WEAK_DISPLACEMENT = "WEAK_DISPLACEMENT"
MODERATE_DISPLACEMENT = "MODERATE_DISPLACEMENT"
STRONG_DISPLACEMENT = "STRONG_DISPLACEMENT"

ORDER = {NO_DISPLACEMENT: 0, WEAK_DISPLACEMENT: 1, MODERATE_DISPLACEMENT: 2, STRONG_DISPLACEMENT: 3}


@dataclass(frozen=True)
class DisplacementParams:
    weak_atr: float = 0.6        # run beyond sweep close >= x * ATR
    moderate_atr: float = 1.0
    strong_atr: float = 1.6
    window: int = 3              # bars after the sweep bar in which the impulse must appear
    min_dir_candles: int = 2     # consecutive candles in impulse direction (moderate/strong)


def measure_displacement(
    df: pd.DataFrame,
    atr: np.ndarray,
    sweep_index: int,
    direction: int,
    params: DisplacementParams = DisplacementParams(),
) -> tuple[str, dict]:
    """Measure the impulse after a sweep.

    direction: +1 expected bullish impulse (sell-side swept),
               -1 expected bearish impulse (buy-side swept).
    Only bars AFTER the sweep bar are used; everything is known at the close
    of the last bar of the window.
    """
    end = min(sweep_index + params.window, len(df) - 1)
    atr_v = float(atr[sweep_index])
    if end <= sweep_index or atr_v <= 0:
        return NO_DISPLACEMENT, {"run_atr": 0.0, "best_body_atr": 0.0, "dir_candles": 0}

    sl_ = slice(sweep_index + 1, end + 1)
    closes = df["close"].iloc[sl_].to_numpy(dtype=float)
    opens = df["open"].iloc[sl_].to_numpy(dtype=float)
    highs = df["high"].iloc[sl_].to_numpy(dtype=float)
    lows = df["low"].iloc[sl_].to_numpy(dtype=float)

    run_price = (float(df["close"].iloc[end]) - float(df["close"].iloc[sweep_index])) * direction
    run_atr = run_price / atr_v

    bodies = np.where(direction > 0, closes - opens, opens - closes)
    best_body_atr = float(bodies.max()) / atr_v if len(bodies) else 0.0

    dir_bars = np.where(direction > 0, closes > opens, closes < opens)
    # longest consecutive run of directional candles
    best_run = run = 0
    for flag in dir_bars:
        run = run + 1 if flag else 0
        best_run = max(best_run, run)

    range_atr = (float(highs.max()) - float(lows.min())) / atr_v
    metrics = {
        "run_atr": float(run_atr),
        "best_body_atr": best_body_atr,
        "range_atr": float(range_atr),
        "dir_candles": int(best_run),
    }

    if run_atr >= params.strong_atr and best_run >= params.min_dir_candles:
        return STRONG_DISPLACEMENT, metrics
    if run_atr >= params.moderate_atr and best_run >= params.min_dir_candles:
        return MODERATE_DISPLACEMENT, metrics
    if run_atr >= params.weak_atr:
        return WEAK_DISPLACEMENT, metrics
    return NO_DISPLACEMENT, metrics
