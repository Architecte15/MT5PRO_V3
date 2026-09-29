import pandas as pd
from app.strategy.market_structure import SwingPoint
from app.strategy.trendline import build_trendline
from app.strategy.breakout import detect_breakout
from app.utils.enums import Direction, SwingType


def test_breakout_requires_close_beyond_buffer():
    swings = [
        SwingPoint(pd.Timestamp("2026-01-01"), 1.0000, 0, SwingType.LOW, True),
        SwingPoint(pd.Timestamp("2026-01-02"), 1.0010, 1, SwingType.LOW, True),
    ]
    tl = build_trendline(swings, Direction.BUY)
    df = pd.DataFrame([{"open":1.001,"high":1.003,"low":1.000,"close":1.0005}])
    assert detect_breakout(df, tl, Direction.BUY, 10, 0.0001) is None
    df.loc[0,"close"] = 1.002
    assert detect_breakout(df, tl, Direction.BUY, 10, 0.0001) is not None
