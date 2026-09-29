import pandas as pd
from app.strategy.divergence import rsi_divergence
from app.strategy.market_structure import SwingPoint
from app.utils.enums import SwingType


def test_bullish_rsi_divergence_on_confirmed_lows():
    idx = pd.date_range("2026-01-01", periods=12, freq="h")
    df = pd.DataFrame({"rsi":[50,50,50,40,50,50,50,45,50,50,50,50]}, index=idx)
    swings=[
        SwingPoint(idx[3], 100, 3, SwingType.LOW, True),
        SwingPoint(idx[7], 99, 7, SwingType.LOW, True),
    ]
    out = rsi_divergence(df, swings, 20)
    assert out.bullish
