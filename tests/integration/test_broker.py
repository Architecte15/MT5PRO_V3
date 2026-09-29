from app.execution.mock_broker import MockBroker
from app.utils.enums import Direction, OrderStatus


def test_mock_broker_order_lifecycle():
    b = MockBroker(); b.connect()
    r = b.send_market_order("EURUSD", Direction.BUY, 0.1, 1.09, 1.12, "TEST")
    assert r.status is OrderStatus.FILLED
    assert len(b.get_positions("EURUSD")) == 1
    b.modify_position(r.position_id, sl=1.095)
    b.partial_close(r.position_id, 0.05)
    assert b.get_positions("EURUSD")[0].volume == 0.05
    b.close_position(r.position_id)
    assert not b.get_positions("EURUSD")
