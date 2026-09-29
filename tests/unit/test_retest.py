import pandas as pd
from app.strategy.retest import detect_retest
from app.utils.enums import Direction


def test_retest_detected():
    df = pd.DataFrame([
        {"open": 10, "high": 11, "low": 9, "close": 10},
        {"open": 11, "high": 12, "low": 10.1, "close": 11.5},
        {"open": 11.5, "high": 11.7, "low": 10.0, "close": 11.2},
    ])
    r = detect_retest(df, Direction.BUY, 10.0, 5, 0.1, 10, 0)
    assert r.detected
