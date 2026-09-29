"""Unit tests: forward labels must never read the past-or-current bar (§11)."""

import numpy as np
import pandas as pd

from app.research.labels import forward_labels


def make_frame(closes):
    n = len(closes)
    c = np.asarray(closes, dtype=float)
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + 0.0002
    l = np.minimum(o, c) - 0.0002
    idx = pd.date_range("2026-06-01 00:00", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                         "volume": 1.0, "spread": 5}, index=idx)


def test_future_return_uses_close_i_and_close_i_plus_horizon_only():
    base = np.linspace(1.10, 1.11, 60)
    df = make_frame(base)
    h = 10
    lab = forward_labels(df, horizon=h)
    i = 20
    assert lab["future_return"].iloc[i] == base[i + h] - base[i]

    # perturbing a bar strictly between i and i+h must not change the label
    base2 = base.copy()
    base2[i + 5] += 0.005
    lab2 = forward_labels(make_frame(base2), horizon=h)
    assert lab2["future_return"].iloc[i] == lab["future_return"].iloc[i]

    # perturbing the target bar must change it
    base3 = base.copy()
    base3[i + h] += 0.005
    lab3 = forward_labels(make_frame(base3), horizon=h)
    assert lab3["future_return"].iloc[i] != lab["future_return"].iloc[i]


def test_mfe_mae_ignore_current_bar_extremes():
    base = np.full(40, 1.1000)
    df = make_frame(base)
    df.loc[df.index[10], "high"] = 1.1200      # spike ON the signal bar itself
    lab = forward_labels(df, horizon=5)
    assert lab["mfe_long"].iloc[10] < 0.001    # not contaminated by bar 10's own spike


def test_mfe_uses_future_highs_within_horizon():
    base = np.full(40, 1.1000)
    df = make_frame(base)
    df.loc[df.index[13], "high"] = 1.1040      # within horizon of bar 10 (h=5 -> 11..15)
    lab = forward_labels(df, horizon=5)
    assert abs(lab["mfe_long"].iloc[10] - (1.1040 - 1.1000)) < 1e-9
    # default synthetic wick is 0.0002 below close; no deeper low in horizon
    assert abs(lab["mae_long"].iloc[10] - 0.0002) < 1e-9


def test_tail_is_nan_beyond_available_horizon():
    base = np.linspace(1.10, 1.11, 50)
    lab = forward_labels(make_frame(base), horizon=7)
    assert lab["future_return"].iloc[-7:].isna().all()
    assert lab["future_return"].iloc[-8] == base[-1] - base[-8]
    assert lab["mfe_long"].iloc[-7:].isna().all()
