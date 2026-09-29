"""Entry construction: SL/TP variants and trade simulation (spec sections 9-10).

SL variants:  ENTRY_SIGNAL_CANDLE / SWEEP_EXTREME / STRUCTURE / ATR_BASED
TP variants:  FIXED_RR / OPPOSITE_LIQUIDITY / TIME_EXIT (no TP)

Rules that mirror the live/backtest engine (never weakened here):
- signal on a CLOSED bar, entry at the OPEN of the next bar (no lookahead);
- a stop already crossed at the entry open invalidates the candidate;
- if SL and TP are touched inside the same bar, SL is assumed first
  (conservative, same convention as app.backtest.engine).
ENTRY_SIGNAL_CANDLE uses the SIGNAL (closed) candle, not the entry candle:
the entry candle's low/high is unknown at entry time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.research.zones import BUY_SIDE, SELL_SIDE, LiquidityZone

ENTRY_SIGNAL_CANDLE = "ENTRY_SIGNAL_CANDLE"
SWEEP_EXTREME = "SWEEP_EXTREME"
STRUCTURE = "STRUCTURE"
ATR_BASED = "ATR_BASED"

TP_FIXED_RR = "FIXED_RR"
TP_OPPOSITE_LIQUIDITY = "OPPOSITE_LIQUIDITY"
TP_TIME_EXIT = "TIME_EXIT"


def compute_sl(
    mode: str,
    df: pd.DataFrame,
    signal_index: int,
    direction: int,
    buffer: float,
    atr_value: float = 0.0,
    atr_mult: float = 1.5,
    sweep_index: int | None = None,
    swings: list | None = None,
    swing_strength: int = 2,
    entry_price: float | None = None,
) -> float | None:
    if mode == ENTRY_SIGNAL_CANDLE:
        return float(df["low"].iloc[signal_index]) - buffer if direction > 0 else float(df["high"].iloc[signal_index]) + buffer
    if mode == SWEEP_EXTREME:
        if sweep_index is None:
            return None
        return float(df["low"].iloc[sweep_index]) - buffer if direction > 0 else float(df["high"].iloc[sweep_index]) + buffer
    if mode == STRUCTURE:
        if not swings:
            return None
        avail = [s for s in swings if s.index + swing_strength <= signal_index]
        if direction > 0:
            lows = [s for s in avail if s.type.value == "LOW"]
            return (float(lows[-1].price) - buffer) if lows else None
        highs = [s for s in avail if s.type.value == "HIGH"]
        return (float(highs[-1].price) + buffer) if highs else None
    if mode == ATR_BASED:
        if entry_price is None or atr_value <= 0:
            return None
        return entry_price - atr_mult * atr_value if direction > 0 else entry_price + atr_mult * atr_value
    raise ValueError(f"Unknown SL mode: {mode}")


def compute_tp(mode: str, direction: int, entry: float, sl: float, rr: float) -> float | None:
    if mode == TP_TIME_EXIT:
        return None
    risk = abs(entry - sl)
    if mode == TP_FIXED_RR:
        return entry + risk * rr if direction > 0 else entry - risk * rr
    raise ValueError(f"TP mode {mode} needs nearest_opposite_liquidity handling (see runner)")


def nearest_opposite_liquidity(
    zones: list[LiquidityZone],
    direction: int,
    entry: float,
    decision_close: pd.Timestamp,
    min_distance: float,
) -> LiquidityZone | None:
    """Nearest available opposite-side zone BEYOND the entry (liquidity target)."""
    side = BUY_SIDE if direction > 0 else SELL_SIDE
    candidates = [
        z for z in zones
        if z.zone_type == side and z.available_at <= decision_close
        and (z.price - entry if direction > 0 else entry - z.price) >= min_distance
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda z: z.price) if direction > 0 else max(candidates, key=lambda z: z.price)


def simulate_trade(
    df: pd.DataFrame,
    signal_index: int,
    direction: int,
    sl: float,
    tp: float | None,
    horizon: int,
) -> dict | None:
    """Fill at the open of signal_index+1 and manage SL/TP/TIME over `horizon` bars."""
    e = signal_index + 1
    if e >= len(df):
        return None
    entry = float(df["open"].iloc[e])
    if direction > 0 and sl >= entry:
        return None
    if direction < 0 and sl <= entry:
        return None

    last = min(e + horizon - 1, len(df) - 1)
    mfe = mae = 0.0
    exit_price: float | None = None
    reason = "TIME"
    exit_index = last

    for j in range(e, last + 1):
        hi = float(df["high"].iloc[j])
        lo = float(df["low"].iloc[j])
        if direction > 0:
            mfe = max(mfe, hi - entry)
            mae = max(mae, entry - lo)
            if lo <= sl:
                exit_price, reason, exit_index = sl, "SL", j
                break
            if tp is not None and hi >= tp:
                exit_price, reason, exit_index = tp, "TP", j
                break
        else:
            mfe = max(mfe, entry - lo)
            mae = max(mae, hi - entry)
            if hi >= sl:
                exit_price, reason, exit_index = sl, "SL", j
                break
            if tp is not None and lo <= tp:
                exit_price, reason, exit_index = tp, "TP", j
                break

    if exit_price is None:
        exit_price = float(df["close"].iloc[last])
        reason = "TIME"
        exit_index = last

    pnl = (exit_price - entry) * direction
    return {
        "entry_index": e,
        "entry_time": pd.Timestamp(df.index[e]),
        "exit_time": pd.Timestamp(df.index[exit_index]),
        "entry": entry,
        "exit": exit_price,
        "sl": sl,
        "tp": tp if tp is not None else float("nan"),
        "pnl": float(pnl),
        "reason": reason,
        "bars_held": int(exit_index - e + 1),
        "mfe": float(mfe),
        "mae": float(mae),
    }
