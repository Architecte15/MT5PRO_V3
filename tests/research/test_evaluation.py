"""Unit tests: splits, bootstrap CI, metrics, controls summary, verdict policy."""

import numpy as np
import pandas as pd
import pytest

from app.research import evaluation as ev


def _times(n=500):
    return pd.Series(pd.date_range("2026-01-01", periods=n, freq="3h", tz="UTC"))


def test_time_splits_are_disjoint_and_exhaustive():
    t = _times()
    masks, boundaries = ev.time_split_masks(t)
    stack = np.stack(list(masks.values()))
    assert np.all(stack.sum(axis=0) == 1)          # exactly one split per row
    order = ["train", "validation", "oos", "holdout"]
    for a, b in zip(order, order[1:]):
        assert t[masks[a]].max() < t[masks[b]].min()
    assert boundaries["t0"] <= boundaries["train_end"] <= boundaries["validation_end"] \
        <= boundaries["oos_end"] <= boundaries["t1"]


def test_time_splits_on_empty_input_do_not_crash():
    empty = pd.Series([], dtype="datetime64[ns, UTC]")
    masks, _ = ev.time_split_masks(empty)
    assert all(len(m) == 0 for m in masks.values())


def test_walk_forward_train_always_strictly_before_test():
    t = _times()
    folds = ev.walk_forward_masks(t, folds=4, initial_train=0.4, test_frac=0.125)
    assert len(folds) == 4
    for tr, te, _ in folds:
        if tr.any() and te.any():
            assert t[tr].max() < t[te].min()
    # holdout zone (last 10%) never used by walk-forward tests
    last_fold_test_end = t[folds[-1][1]].max()
    assert last_fold_test_end <= t.max() - (t.max() - t.min()) * 0.09


def test_bootstrap_ci_deterministic_and_contains_mean():
    vals = [0.1, -0.05, 0.2, 0.05, -0.1, 0.15, 0.0, 0.08]
    a = ev.bootstrap_ci(vals, seed=42)
    b = ev.bootstrap_ci(vals, seed=42)
    assert a == b
    m = float(np.mean(vals))
    assert a[0] <= m <= a[1]
    assert ev.bootstrap_ci([], seed=1)[0] != ev.bootstrap_ci([], seed=1)[0]  # NaN
    single = ev.bootstrap_ci([0.3], seed=1)
    assert single == (0.3, 0.3)


def test_trade_metrics_correct_on_known_series():
    trades = pd.DataFrame({"pnl": [1.0, -0.5, 2.0, -1.0],
                           "mfe": [1.2, 0.1, 2.5, 0.2],
                           "mae": [0.1, 0.6, 0.2, 1.1],
                           "bars_held": [4, 8, 2, 6],
                           "reason": ["TP", "SL", "TP", "SL"]})
    m = ev.trade_metrics(trades)
    assert m["n"] == 4
    assert m["wins"] == 2
    assert m["win_rate"] == 0.5
    assert m["expectancy"] == 0.375
    assert m["gross_profit"] == 3.0
    assert m["gross_loss"] == 1.5
    assert m["profit_factor"] == 2.0
    assert m["payoff"] == 2.0
    assert m["max_drawdown"] == 1.0        # cumsum [1, .5, 2.5, 1.5], peak-cum = 1.0
    assert m["sl_exits"] == 2 and m["tp_exits"] == 2


def test_trade_metrics_empty_frame():
    m = ev.trade_metrics(pd.DataFrame())
    assert m["n"] == 0


def test_breakeven_wr_formula():
    assert ev.breakeven_wr(1, 1) == 0.5
    assert ev.breakeven_wr(1, 3) == 0.25
    assert ev.breakeven_wr(0, 0) != ev.breakeven_wr(0, 0)   # NaN


def test_control_summary_detects_beating_real():
    draws = [np.array([0.01, 0.02]), np.array([0.0, 0.01])]
    s = ev.control_summary(draws, real_expectancy=0.005)
    assert s["draws"] == 2
    assert 0 <= s["share_draws_ge_real"] <= 1
    assert s["mean_expectancy"] == pytest.approx(np.mean([0.015, 0.005]))


def test_verdict_policy_edges_not_found():
    good = {"n": 50, "expectancy": 0.002, "profit_factor": 1.8,
            "win_rate": 0.5, "max_drawdown": 0.01}
    # all gates pass -> CANDIDATE
    v, reasons = ev.verdict(good, (0.0005, 0.004), 4, 4, 0.001, 30)
    assert v.startswith("CANDIDATE")
    # too few trades
    v, reasons = ev.verdict({**good, "n": 12}, (0.0005, 0.004), 4, 4, 0.001, 30)
    assert v == "EDGE NOT FOUND" and any("n=" in r for r in reasons)
    # CI includes 0
    v, reasons = ev.verdict(good, (-0.0001, 0.004), 4, 4, 0.001, 30)
    assert v == "EDGE NOT FOUND" and any("CI" in r for r in reasons)
    # does not beat controls
    v, reasons = ev.verdict(good, (0.0005, 0.004), 4, 4, 0.01, 30)
    assert v == "EDGE NOT FOUND" and any("control" in r for r in reasons)
    # unstable walk-forward
    v, reasons = ev.verdict(good, (0.0005, 0.004), 2, 4, 0.001, 30)
    assert v == "EDGE NOT FOUND" and any("walk-forward" in r for r in reasons)


def test_hash_preregistration_stable_and_sensitive():
    h1 = ev.hash_preregistration({"a": 1, "b": [1, 2]})
    h2 = ev.hash_preregistration({"b": [1, 2], "a": 1})
    h3 = ev.hash_preregistration({"a": 1, "b": [1, 3]})
    assert h1 == h2          # key order independent
    assert h1 != h3          # content sensitive
