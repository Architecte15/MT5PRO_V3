from app.config.models import PositionManagementConfig
from app.risk.stop_manager import StopManager
from app.utils.enums import Direction


def test_break_even():
    cfg = PositionManagementConfig(enable_break_even=True, break_even_trigger_points=10, break_even_offset_points=1, enable_trailing_stop=False)
    sm = StopManager(cfg)
    out = sm.update("1", Direction.BUY, 1.1000, 1.1015, 1.0950, 0.0050, 0.0001)
    assert out.new_sl is not None
