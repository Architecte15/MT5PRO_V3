from app.execution.mt5_broker import MT5Broker


class FakeMT5:
    ORDER_FILLING_FOK = 10
    ORDER_FILLING_IOC = 11
    ORDER_FILLING_RETURN = 12

    class Info:
        def __init__(self, mode): self.filling_mode = mode

    def __init__(self, mode): self.mode = mode
    def symbol_info(self, symbol): return self.Info(self.mode)


def make(mode):
    broker = object.__new__(MT5Broker)
    broker.mt5 = FakeMT5(mode)
    return broker


def test_filling_mode_prefers_fok():
    assert make(1)._filling_mode("EURUSD") == 10


def test_filling_mode_uses_ioc_when_fok_unavailable():
    assert make(2)._filling_mode("EURUSD") == 11


def test_filling_mode_falls_back_to_return():
    assert make(0)._filling_mode("EURUSD") == 12
