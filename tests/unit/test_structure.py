import pandas as pd

from app.strategy.market_structure import detect_swings, classify_structure
from app.strategy.trendline import build_trendline
from app.utils.enums import Direction, SwingType, Trend


def test_detect_and_classify_bullish_structure():
    idx = pd.date_range("2026-01-01", periods=30, freq="h")
    close = [100, 99, 101, 100, 103, 101, 105, 103, 107, 105, 109, 107, 111, 109, 113, 111, 115, 113, 117, 115, 119, 117, 121, 119, 123, 121, 125, 123, 127, 125]
    df = pd.DataFrame({"open": close, "high": [x+1 for x in close], "low": [x-1 for x in close], "close": close}, index=idx)
    swings = detect_swings(df, 1)
    structure = classify_structure(swings)
    assert structure.trend in (Trend.BULLISH, Trend.NEUTRAL)


def test_trendline_math():
    swings = [
        type("S", (), {"price": 10.0, "index": 1, "type": SwingType.LOW, "confirmed": True, "timestamp": 1})(),
        type("S", (), {"price": 14.0, "index": 3, "type": SwingType.LOW, "confirmed": True, "timestamp": 3})(),
    ]
    tl = build_trendline(swings, Direction.BUY)
    assert tl is not None
    assert tl.slope == 2.0
    assert tl.value_at(4) == 16.0
