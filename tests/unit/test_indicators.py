import numpy as np
import pandas as pd

from app.strategy.indicators import ema, bollinger_bands, rsi, macd


def test_ema_constant():
    s = pd.Series([10.0] * 30)
    assert ema(s, 5).dropna().eq(10.0).all()


def test_bollinger_center_constant():
    s = pd.Series([5.0] * 30)
    bb = bollinger_bands(s, 5, 2)
    assert np.isclose(bb.iloc[-1].bb_middle, 5.0)
    assert np.isclose(bb.iloc[-1].bb_upper, 5.0)
    assert np.isclose(bb.iloc[-1].bb_lower, 5.0)


def test_rsi_bounds():
    s = pd.Series(np.arange(1, 50, dtype=float))
    out = rsi(s, 14).dropna()
    assert out.between(0, 100).all()


def test_macd_columns():
    s = pd.Series(np.linspace(1, 2, 100))
    out = macd(s)
    assert {"macd_main", "macd_signal", "macd_hist"} == set(out.columns)
