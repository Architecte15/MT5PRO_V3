"""Unit tests: entry construction — SL/TP variants, simulation rules (spec §9-10).

Covers: next-open fill, SL-first on same bar, stop-side validation, MFE/MAE,
horizon time exit, and each SL mode's no-lookahead semantics.
"""

import numpy as np
import pandas as pd

from app.research.entries import (
    ATR_BASED,
    ENTRY_SIGNAL_CANDLE,
    STRUCTURE,
    SWEEP_EXTREME,
    TP_FIXED_RR,
    TP_TIME_EXIT,
    compute_sl,
    compute_tp,
    nearest_opposite_liquidity,
    simulate_trade,
)
from app.research.zones import BUY_SIDE, KIND_SWING, LiquidityZone
from app.strategy.market_structure import SwingPoint
from app.utils.enums import SwingType


def make_frame():
    c = np.array([1.1000, 1.1005, 1.1010, 1.1008, 1.1006, 1.1004,
                  1.1002, 1.1000, 1.0998, 1.0996, 1.0994, 1.0992])
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + 0.0003
    l = np.minimum(o, c) - 0.0003
    idx = pd.date_range("2026-05-04 00:00", periods=len(c), freq="15min", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                         "volume": 100.0, "spread": 10}, index=idx)


def test_entry_at_next_open_and_time_exit():
    df = make_frame()
    r = simulate_trade(df, signal_index=1, direction=1, sl=1.0990, tp=1.1020, horizon=6)
    assert r is not None
    assert r["entry"] == float(df["open"].iloc[2])       # fill at open after signal
    assert r["entry_index"] == 2
    assert r["reason"] == "TIME"
    assert r["exit"] == float(df["close"].iloc[7])       # signal1 +1 +6-1 = 7
    assert r["bars_held"] == 6
    assert r["pnl"] == (1.1000 - 1.1005)
    # MFE/MAE measured over bars 2..7 only
    assert abs(r["mfe"] - (df["high"].iloc[2:8].max() - 1.1005)) < 1e-12
    assert abs(r["mae"] - (1.1005 - df["low"].iloc[2:8].min())) < 1e-12


def test_sl_wins_over_tp_inside_same_bar():
    df = make_frame()
    df.loc[df.index[4], "high"] = 1.1025      # TP 1.1020 touched
    df.loc[df.index[4], "low"] = 1.0985       # SL 1.0990 touched in the same bar
    r = simulate_trade(df, signal_index=1, direction=1, sl=1.0990, tp=1.1020, horizon=6)
    assert r["reason"] == "SL"
    assert r["exit"] == 1.0990
    assert r["pnl"] < 0


def test_stop_already_crossed_at_entry_rejects_candidate():
    df = make_frame()
    # BUY with stop above the entry open (1.1010): invalid side -> rejected
    assert simulate_trade(df, signal_index=1, direction=1, sl=1.1010, tp=None, horizon=6) is None
    # SELL with stop below entry open: invalid side -> rejected
    assert simulate_trade(df, signal_index=1, direction=-1, sl=1.1000, tp=None, horizon=6) is None


def test_sell_trade_pnl_sign():
    df = make_frame()
    sl, tp = 1.1025, 1.1000
    r = simulate_trade(df, signal_index=6, direction=-1, sl=sl, tp=tp, horizon=6)
    assert r is not None
    entry = float(df["open"].iloc[7])            # = 1.1002
    assert r["reason"] == "TP"                   # bar 7 low dips to 1.0995 <= 1.1000
    assert r["exit"] == tp
    assert abs(r["pnl"] - (tp - entry) * -1) < 1e-15   # short gains when price falls
    assert r["pnl"] > 0


def test_sl_modes_are_no_lookahead():
    df = make_frame()
    signal = 6
    # signal-candle mode uses the CLOSED signal bar, never the entry bar (7)
    sl_buy = compute_sl(ENTRY_SIGNAL_CANDLE, df, signal, 1, buffer=0.00005)
    assert abs(sl_buy - (float(df["low"].iloc[6]) - 0.00005)) < 1e-12
    # sweep-extreme mode uses the recorded sweep bar (0)
    sl_sw = compute_sl(SWEEP_EXTREME, df, signal, 1, buffer=0.00005, sweep_index=0)
    assert abs(sl_sw - (float(df["low"].iloc[0]) - 0.00005)) < 1e-12
    # ATR mode needs the entry price (entry is next open)
    entry = float(df["open"].iloc[signal + 1])
    sl_atr = compute_sl(ATR_BASED, df, signal, 1, buffer=0.0, atr_value=0.0010,
                        atr_mult=1.5, entry_price=entry)
    assert abs(sl_atr - (entry - 0.0015)) < 1e-12
    # structure mode: only swings confirmed by the signal bar count
    ts = pd.Timestamp(df.index[3])
    swing = SwingPoint(ts, 1.0950, 3, SwingType.LOW, True)
    sl_st = compute_sl(STRUCTURE, df, signal, 1, buffer=0.00005,
                       swings=[swing], swing_strength=2)
    assert abs(sl_st - (1.0950 - 0.00005)) < 1e-12
    future_swing = SwingPoint(pd.Timestamp(df.index[10]), 1.0960, 10, SwingType.LOW, True)
    sl_st2 = compute_sl(STRUCTURE, df, signal, 1, buffer=0.0,
                        swings=[swing, future_swing], swing_strength=2)
    assert abs(sl_st2 - 1.0950) < 1e-12     # future swing (index10 > signal6) ignored
    # no swings available -> None
    assert compute_sl(STRUCTURE, df, signal, 1, buffer=0.0, swings=[], swing_strength=2) is None


def test_tp_variants():
    assert compute_tp(TP_FIXED_RR, 1, 1.1000, 1.0990, rr=2.0) == 1.1019999999999999 or \
        abs(compute_tp(TP_FIXED_RR, 1, 1.1000, 1.0990, rr=2.0) - 1.1020) < 1e-12
    assert abs(compute_tp(TP_FIXED_RR, -1, 1.1000, 1.1010, rr=2.0) - 1.0980) < 1e-12
    assert compute_tp(TP_TIME_EXIT, 1, 1.1000, 1.0990, rr=2.0) is None


def test_nearest_opposite_liquidity_avoids_future_zones():
    df = make_frame()
    decision = pd.Timestamp(df.index[6]) + pd.Timedelta(minutes=15)
    known = LiquidityZone("a", BUY_SIDE, "M15", 1.1050, 0,
                          df.index[0], df.index[2], KIND_SWING)
    below = LiquidityZone("b", BUY_SIDE, "M15", 1.0900, 0,
                          df.index[0], df.index[2], KIND_SWING)      # below entry
    future = LiquidityZone("c", BUY_SIDE, "M15", 1.1030, 0,
                           df.index[0], df.index[9], KIND_SWING)     # not yet known
    z = nearest_opposite_liquidity([known, below, future], 1, 1.1010, decision,
                                   min_distance=0.00005)
    assert z is not None and abs(z.price - 1.1050) < 1e-12
    # when only unknown/behind zones exist -> no target
    assert nearest_opposite_liquidity([below, future], 1, 1.1010, decision,
                                      min_distance=0.00005) is None
