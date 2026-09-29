"""Unit tests: structure events (spec section 5) — no-lookahead invariant.

A break can only be emitted against a swing that is already CONFIRMED at that
bar (swing index + strength <= event index).
"""

import numpy as np
import pandas as pd

from app.research.structure import detect_structure_events


def make_frame(closes, highs, lows, start="2026-04-06 00:00"):
    n = len(closes)
    idx = pd.date_range(start, periods=n, freq="15min", tz="UTC")
    c = np.asarray(closes, dtype=float)
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame(
        {"open": o, "high": np.asarray(highs, float), "low": np.asarray(lows, float),
         "close": c, "volume": 100.0, "spread": 10},
        index=idx,
    )


def _frame():
    n = 60
    closes = np.full(n, 1.1000)
    highs = np.full(n, 1.1002)
    lows = np.full(n, 1.0998)
    highs[5] = 1.1050            # swing high, knowable at bar 7
    lows[10] = 1.0950            # swing low, knowable at bar 12
    closes[6] = 1.1060           # crosses the swing high BEFORE it is known
    closes[7] = 1.1000           # back below
    closes[8] = 1.1060           # first break AFTER confirmation -> event here
    closes[9:] = 1.1000
    return make_frame(closes, highs, lows)


def test_no_event_before_swing_confirmation():
    df = _frame()
    events = detect_structure_events(df, swing_strength=2)
    # bar 6 crosses the level but the swing is not yet confirmed -> no event
    assert all(e.index != 6 for e in events)
    assert events, "expected a structure break after confirmation"
    assert events[0].index >= 7


def test_first_break_emitted_as_bos_up_with_known_level():
    df = _frame()
    events = detect_structure_events(df, swing_strength=2)
    e = events[0]
    assert e.index == 8
    assert e.kind == "BOS"
    assert e.direction == "UP"
    assert abs(e.level - 1.1050) < 1e-12


def test_every_event_level_belongs_to_a_confirmed_swing():
    n = 200
    rng = np.random.default_rng(7)
    closes = 1.10 + np.cumsum(rng.normal(0, 0.0004, n))
    prev = np.r_[closes[0], closes[:-1]]
    highs = np.maximum(prev, closes) + rng.uniform(0.0001, 0.0006, n)
    lows = np.minimum(prev, closes) - rng.uniform(0.0001, 0.0006, n)
    df = make_frame(closes, highs, lows)

    strength = 2
    from app.strategy.market_structure import detect_swings
    swings = detect_swings(df, strength)
    swing_levels = {(s.index, round(s.price, 8)) for s in swings}

    events = detect_structure_events(df, swing_strength=strength)
    assert events
    for e in events:
        # level must come from a swing confirmed at or before the event bar
        confirmed = [lvl for (sidx, lvl) in swing_levels
                     if abs(lvl - round(e.level, 8)) == 0 and sidx + strength <= e.index]
        assert confirmed, f"event {e.index} uses a level that was not yet known"
