import pandas as pd
from app.backtest.engine import BacktestEngine
from app.config.models import AppConfig


def test_backtest_empty_is_safe():
    idx = pd.date_range("2026-01-01", periods=100, freq="h")
    close = pd.Series(range(100), dtype=float) + 100
    df = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close}, index=idx)
    result = BacktestEngine(AppConfig()).run(df, df)
    assert "total_trades" in result.metrics
