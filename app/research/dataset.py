"""Observation dataset builder (spec section 11).

One row per M15 candle with everything knowable at that candle's close plus,
in clearly separated columns, the forward outcome after the horizon. Outcome
columns exist for memory/training purposes only (spec sections 11-14) and must
never be joined into anything used for entry decisions.
"""

from __future__ import annotations

import bisect

import numpy as np
import pandas as pd

from app.research.labels import forward_labels
from app.research.regime import classify_regimes, classify_volatility, fit_volatility_thresholds
from app.research.structure import detect_structure_events
from app.research.zones import BUY_SIDE, LiquidityZone


def nearest_liquidity_series(
    df: pd.DataFrame,
    zones: list[LiquidityZone],
) -> tuple[pd.Series, pd.Series]:
    """Nearest available buy-side zone ABOVE price / sell-side zone BELOW price.

    A zone only enters the map from its available_at close (no lookahead).
    """
    decision_close = pd.DatetimeIndex(df.index) + pd.Timedelta(minutes=15)
    ordered = sorted(zones, key=lambda z: z.available_at)

    buy_sorted: list[float] = []
    sell_sorted: list[float] = []
    cursor = 0
    nearest_buy = np.full(len(df), np.nan)
    nearest_sell = np.full(len(df), np.nan)
    close_arr = df["close"].to_numpy(dtype=float)

    for i in range(len(df)):
        while cursor < len(ordered) and ordered[cursor].available_at <= decision_close[i]:
            z = ordered[cursor]
            if z.zone_type == BUY_SIDE:
                bisect.insort(buy_sorted, z.price)
            else:
                bisect.insort(sell_sorted, z.price)
            cursor += 1
        close = float(close_arr[i])
        j = bisect.bisect_right(buy_sorted, close)     # first zone strictly above
        if j < len(buy_sorted):
            nearest_buy[i] = buy_sorted[j]
        k = bisect.bisect_left(sell_sorted, close)     # last zone strictly below
        if k > 0:
            nearest_sell[i] = sell_sorted[k - 1]

    return (
        pd.Series(nearest_buy, index=df.index, name="nearest_buy_liquidity"),
        pd.Series(nearest_sell, index=df.index, name="nearest_sell_liquidity"),
    )


def build_observations(
    df: pd.DataFrame,
    features: pd.DataFrame,
    zones: list[LiquidityZone],
    sweeps: list,                 # list[SweepEvent]
    atr: pd.Series,
    horizon: int = 96,
    stop_atr_mult: float = 1.5,
    target_rr: float = 2.0,
    vol_train_frac: float = 0.6,
) -> pd.DataFrame:
    """Per-candle observation frame: features + liquidity map + event flags + outcomes."""
    out = features.copy()
    pos = {ts: i for i, ts in enumerate(df.index)}

    # --- regime (volatility thresholds fit on TRAIN period only) ------------
    t0, t1 = df.index[0], df.index[-1]
    b1 = t0 + (t1 - t0) * vol_train_frac
    vol_hi, vol_lo = fit_volatility_thresholds(features["atr_pct"].loc[:b1])
    out["regime"] = classify_regimes(df, atr)
    out["volatility_regime"] = classify_volatility(features["atr_pct"], vol_hi, vol_lo)

    # --- liquidity map ------------------------------------------------------
    nearest_buy, nearest_sell = nearest_liquidity_series(df, zones)
    out["nearest_buy_liquidity"] = nearest_buy
    out["nearest_sell_liquidity"] = nearest_sell
    out["dist_to_buy_liquidity"] = nearest_buy - df["close"]
    out["dist_to_sell_liquidity"] = df["close"] - nearest_sell

    # --- sweep flags --------------------------------------------------------
    out["liquidity_swept"] = False
    out["sweep_side"] = ""
    out["sweep_class"] = ""
    out["sweep_strength_atr"] = np.nan
    out["displacement_strength"] = ""
    atr_arr = atr.to_numpy(dtype=float)
    for ev in sweeps:
        i = pos.get(ev.timestamp)
        if i is None:
            continue
        out.iat[i, out.columns.get_loc("liquidity_swept")] = True
        out.iat[i, out.columns.get_loc("sweep_side")] = ev.zone_type
        out.iat[i, out.columns.get_loc("sweep_class")] = ev.sweep_class
        a = float(atr_arr[ev.index])
        out.iat[i, out.columns.get_loc("sweep_strength_atr")] = (
            ev.pierce_distance / a if a > 0 else 0.0
        )
        out.iat[i, out.columns.get_loc("displacement_strength")] = ev.displacement

    # --- structure event labels --------------------------------------------
    out["structure_event"] = ""
    col_struct = out.columns.get_loc("structure_event")
    for ev in detect_structure_events(df):
        i = pos.get(ev.timestamp)
        if i is not None:
            out.iat[i, col_struct] = f"{ev.kind}_{ev.direction}"

    # --- forward outcomes (evaluation/memory ONLY) --------------------------
    out = out.join(forward_labels(df, horizon=horizon))
    hit = _hit_target_hit_stop(df, atr_arr, horizon, stop_atr_mult, target_rr)
    out["hit_stop"] = hit["hit_stop"]
    out["hit_target"] = hit["hit_target"]
    return out


def _hit_target_hit_stop(
    df: pd.DataFrame,
    atr_arr: np.ndarray,
    horizon: int,
    stop_atr_mult: float,
    rr: float,
) -> dict:
    """Reference ±ATR stop / RR target from each bar's close (SL-first per bar).

    Both orientations evaluated: hit_stop = long-stop OR short-stop touched;
    hit_target = long-target OR short-target touched (first-touch, horizon-capped).
    """
    n = len(df)
    closes = df["close"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    hit_stop = np.zeros(n, dtype=bool)
    hit_target = np.zeros(n, dtype=bool)
    for i in range(n - horizon):
        a = float(atr_arr[i])
        if not (a > 0):
            continue
        stop_long = closes[i] - stop_atr_mult * a
        target_long = closes[i] + stop_atr_mult * a * rr
        stop_short = closes[i] + stop_atr_mult * a
        target_short = closes[i] - stop_atr_mult * a * rr
        hs = ht = False
        for j in range(i + 1, i + horizon + 1):
            if lows[j] <= stop_long or highs[j] >= stop_short:
                hs = True
            if highs[j] >= target_long or lows[j] <= target_short:
                ht = True
            if hs or ht:
                break
        hit_stop[i] = hs
        hit_target[i] = ht
    return {"hit_stop": hit_stop, "hit_target": hit_target}
