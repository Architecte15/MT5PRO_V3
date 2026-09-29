import pandas as pd
from app.strategy.market_structure import detect_swings


def test_unconfirmed_current_edges_are_not_swings():
    idx = pd.date_range("2026-01-01", periods=8, freq="h")
    values = [1, 3, 2, 4, 2, 5, 4, 6]
    df = pd.DataFrame({"open": values, "high": values, "low": values, "close": values}, index=idx)
    swings = detect_swings(df, 2)
    assert all(2 <= s.index <= len(df)-3 for s in swings)
