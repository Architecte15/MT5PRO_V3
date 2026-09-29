import pandas as pd
from app.strategy.indicators import has_squeeze_before


def test_squeeze_run():
    s = pd.Series([0.2,0.1,0.05,0.04,0.03,0.02])
    assert has_squeeze_before(s, 10, 0.08, 3)
