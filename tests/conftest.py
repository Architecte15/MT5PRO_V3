import pytest
from tests.fixtures.market_fixtures import make_ohlc


@pytest.fixture
def bullish_df():
    return make_ohlc(350, drift=0.02)


@pytest.fixture
def bearish_df():
    return make_ohlc(350, drift=-0.02)
