import pandas as pd
from app.data.validation import validate_market_frame


def test_market_validation_rejects_duplicates_and_nan():
    idx = pd.DatetimeIndex(["2026-01-01", "2026-01-01"])
    df = pd.DataFrame({"open": [1.0, float('nan')], "high": [1.1, 1.1], "low": [0.9, 0.9], "close": [1.0, 1.0]}, index=idx)
    errors = validate_market_frame(df)
    assert "Duplicate timestamps" in errors
    assert "NaN in OHLC" in errors
