from pathlib import Path


def read(path):
    return Path(path).read_text(encoding="utf-8")


def test_critical_fixes_remain_present():
    breakout = read("app/strategy/breakout.py")
    signal = read("app/strategy/signal_engine.py")
    mt5 = read("app/execution/mt5_broker.py")
    data = read("app/data/mt5_market_data.py")
    report = read("app/backtest/report.py")
    engine = read("app/backtest/engine.py")
    assert "lookback_bars" in breakout and "max_retest_bars + 1" in signal
    assert "def _filling_mode" in mt5 and "ORDER_FILLING_FOK" in mt5
    assert "symbol_select" in data
    assert 'matplotlib.use("Agg")' in report
    assert "self._window = 800" in engine
    range_module = read("app/strategy/range_4h.py")
    assert "America/New_York" in range_module
    assert "close <= rng.high" in range_module and "close >= rng.low" in range_module
    assert "take_profit" in range_module
