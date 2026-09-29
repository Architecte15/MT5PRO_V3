import pandas as pd
from app.utils.validation import validate_ohlc


def test_empty_frame():
    assert "DataFrame is empty" in validate_ohlc(pd.DataFrame())


def test_invalid_nan():
    df = pd.DataFrame({"open": [1.0], "high": [1.1], "low": [0.9], "close": [float('nan')]}, index=pd.date_range('2026-01-01', periods=1, freq='h'))
    assert any("NaN" in e for e in validate_ohlc(df))
