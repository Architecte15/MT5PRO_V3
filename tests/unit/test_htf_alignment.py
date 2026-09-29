import pandas as pd

from app.backtest.engine import BacktestEngine
from app.config.models import AppConfig


def make_h4():
    idx = pd.date_range("2026-01-01", periods=4, freq="4h", tz="UTC")
    return pd.DataFrame({"open": 1.1, "high": 1.11, "low": 1.09, "close": 1.105}, index=idx)


def test_htf_candle_is_unavailable_until_its_close():
    engine = BacktestEngine(AppConfig())
    h4 = make_h4()
    before_close = pd.Timestamp("2026-01-01 03:45:00+00:00")
    at_close = pd.Timestamp("2026-01-01 04:00:00+00:00")
    assert len(engine._closed_htf(h4, before_close)) == 0
    assert len(engine._closed_htf(h4, at_close)) == 1


def test_future_h4_candles_are_never_visible():
    engine = BacktestEngine(AppConfig())
    h4 = make_h4()
    visible = engine._closed_htf(h4, pd.Timestamp("2026-01-01 08:00:00+00:00"))
    assert list(visible.index) == [pd.Timestamp("2026-01-01 00:00:00+00:00"), pd.Timestamp("2026-01-01 04:00:00+00:00")]


def test_htf_ema_input_is_history_only():
    engine = BacktestEngine(AppConfig())
    h4 = make_h4()
    decision_time = pd.Timestamp("2026-01-01 04:00:00+00:00")
    visible = engine._closed_htf(h4, decision_time)
    assert visible.index.max() == pd.Timestamp("2026-01-01 00:00:00+00:00")
