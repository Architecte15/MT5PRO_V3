import pandas as pd

from app.strategy.range_4h import build_first_h4_ranges, detect_range_scalp_signals
from app.utils.enums import Direction


def _h4():
    idx = pd.date_range("2026-01-05 05:00", periods=3, freq="4h", tz="UTC")
    # First bar is 00:00 New York during EST.
    return pd.DataFrame({
        "open": [1.1000, 1.1010, 1.1020],
        "high": [1.1050, 1.1080, 1.1100],
        "low": [1.0950, 1.0990, 1.1000],
        "close": [1.1010, 1.1020, 1.1050],
    }, index=idx)


def _m5():
    idx = pd.date_range("2026-01-05 09:00", periods=8, freq="5min", tz="UTC")
    # First two bars occur after 04:00 NY close of the first H4 bar.
    rows = [
        (1.1000, 1.1020, 1.0990, 1.1010),
        (1.1010, 1.1060, 1.1000, 1.1060),  # close above range high
        (1.1060, 1.1070, 1.0980, 1.1000),  # close back inside => SELL
        (1.1000, 1.1010, 1.0990, 1.1000),
        (1.1000, 1.1010, 1.0940, 1.0940),  # close below range low
        (1.0940, 1.0970, 1.0930, 1.0960),  # inside => BUY
        (1.0960, 1.0970, 1.0950, 1.0960),
        (1.0960, 1.0970, 1.0950, 1.0960),
    ]
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def test_first_h4_range_is_built_from_first_local_day_candle():
    ranges = build_first_h4_ranges(_h4())
    r = ranges["2026-01-05"]
    assert r.high == 1.1050
    assert r.low == 1.0950
    assert r.close_time == pd.Timestamp("2026-01-05 09:00", tz="UTC")


def test_closed_breakout_then_reentry_generates_directional_signals_without_lookahead():
    signals = detect_range_scalp_signals(_m5(), _h4(), max_sl_points=2000)
    assert len(signals) == 2
    assert signals[0].direction is Direction.SELL
    assert signals[1].direction is Direction.BUY
    assert signals[0].entry_time > signals[0].reentry_time
    assert signals[0].take_profit < signals[0].entry_price
    assert signals[1].take_profit > signals[1].entry_price


def test_wick_only_does_not_trigger_breakout():
    m5 = _m5().copy()
    m5.iloc[1, m5.columns.get_loc("close")] = 1.1040
    signals = detect_range_scalp_signals(m5, _h4(), max_sl_points=2000)
    assert all(s.direction is Direction.BUY for s in signals)
