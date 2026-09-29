import pandas as pd

from app.strategy.price_action import analyze_price_action
from app.utils.enums import Direction


def frame(rows):
    return pd.DataFrame(rows)


def test_bullish_engulfing():
    rows = [
        {"open": 10, "high": 11, "low": 9.8, "close": 10.5},
        {"open": 10.4, "high": 10.5, "low": 9.0, "close": 9.2},
        {"open": 9.8, "high": 10.0, "low": 9.2, "close": 9.4},
        {"open": 9.4, "high": 9.6, "low": 9.1, "close": 9.3},
        {"open": 9.0, "high": 11.2, "low": 8.9, "close": 11.0},
    ]
    pa = analyze_price_action(frame(rows), Direction.BUY)
    assert pa.bullish_engulfing
