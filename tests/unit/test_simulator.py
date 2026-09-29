from app.backtest.simulator import check_exit
from app.utils.enums import Direction


def test_invalid_buy_stop_side_is_rejected():
    bar = {"high": 1.1050, "low": 1.0950}
    assert check_exit(Direction.BUY, 1.1000, 1.1005, 1.1100, bar) is None


def test_invalid_sell_stop_side_is_rejected():
    bar = {"high": 1.1050, "low": 1.0950}
    assert check_exit(Direction.SELL, 1.1000, 1.0995, 1.0900, bar) is None
