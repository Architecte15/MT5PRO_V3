from datetime import datetime, timezone

from app.config.models import AppConfig
from app.data.tick import Tick
from app.risk.position_sizer import SymbolSpec, calculate_volume
from app.risk.risk_manager import RiskManager
from app.utils.enums import Direction


def test_position_sizing_respects_risk():
    spec = SymbolSpec(0.00001, 0.00001, 1.0, 100000, 0.01, 100, 0.01)
    vol = calculate_volume(10000, 1.0, 1.1000, 1.0950, spec)
    assert vol > 0
    assert round(vol / 0.01) == vol / 0.01


def test_spread_blocks():
    cfg = AppConfig(point_size=0.00001)
    rm = RiskManager(cfg)
    spec = SymbolSpec(0.00001, 0.00001, 1.0, 100000, 0.01, 100, 0.01)
    tick = Tick(datetime.now(timezone.utc), 1.1000, 1.1020)
    result = rm.assess(Direction.BUY, 1.1020, 1.0970, spec, 10000, 10000, tick, datetime.now(timezone.utc))
    assert not result.accepted
    assert "Spread too high" in result.reasons


def test_buy_rejects_stop_above_or_at_entry():
    cfg = AppConfig(point_size=0.00001)
    rm = RiskManager(cfg)
    spec = SymbolSpec(0.00001, 0.00001, 1.0, 100000, 0.01, 100, 0.01)
    tick = Tick(datetime.now(timezone.utc), 1.1000, 1.1002)
    result = rm.assess(Direction.BUY, 1.1000, 1.1001, spec, 10000, 10000, tick, datetime.now(timezone.utc))
    assert not result.accepted
    assert any("Invalid SL side for BUY" in reason for reason in result.reasons)


def test_sell_rejects_stop_below_or_at_entry():
    cfg = AppConfig(point_size=0.00001)
    rm = RiskManager(cfg)
    spec = SymbolSpec(0.00001, 0.00001, 1.0, 100000, 0.01, 100, 0.01)
    tick = Tick(datetime.now(timezone.utc), 1.1000, 1.1002)
    result = rm.assess(Direction.SELL, 1.1000, 1.0999, spec, 10000, 10000, tick, datetime.now(timezone.utc))
    assert not result.accepted
    assert any("Invalid SL side for SELL" in reason for reason in result.reasons)
