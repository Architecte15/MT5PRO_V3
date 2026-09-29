from pathlib import Path

from app.execution.execution_guard import ExecutionGuard
from app.execution.mock_broker import MockBroker
from app.execution.order_manager import OrderManager
from app.utils.enums import Direction, OrderStatus


def test_execution_guard_deduplicates_same_signal(tmp_path: Path):
    guard = ExecutionGuard(str(tmp_path / "guard.sqlite3"), 10)
    fp = guard.fingerprint("EURUSD", "2026-09-25T12:13:00+00:00", "BUY", "TEST")
    first = guard.claim("EURUSD", fp)
    assert first.acquired
    guard.release("EURUSD")
    second = guard.claim("EURUSD", fp)
    assert not second.acquired
    assert "duplicate signal" in second.reason


def test_execution_guard_serializes_symbol_and_supports_cooldown(tmp_path: Path):
    db = str(tmp_path / "guard.sqlite3")
    g1 = ExecutionGuard(db, 10)
    g2 = ExecutionGuard(db, 10)
    fp1 = g1.fingerprint("EURUSD", "t1", "BUY", "TEST")
    fp2 = g2.fingerprint("EURUSD", "t2", "SELL", "TEST")
    assert g1.claim("EURUSD", fp1).acquired
    assert not g2.claim("EURUSD", fp2).acquired
    g1.release("EURUSD")
    assert g2.claim("EURUSD", fp2).acquired
    g2.release("EURUSD")
    g2.set_cooldown("EURUSD", 30)
    fp3 = g1.fingerprint("EURUSD", "t3", "BUY", "TEST")
    claim = g1.claim("EURUSD", fp3)
    assert not claim.acquired
    assert "cooldown" in claim.reason


def test_order_manager_blocks_duplicate_or_opposite_position():
    broker = MockBroker()
    broker.connect()
    manager = OrderManager(broker, "TEST", max_positions_per_symbol=1, allow_hedging=False, allow_opposite_entry=False)
    first = manager.execute("EURUSD", Direction.BUY, 0.01, 1.09, 1.12)
    assert first.status is OrderStatus.FILLED
    second = manager.execute("EURUSD", Direction.SELL, 0.01, 1.11, 1.08)
    assert second.status is OrderStatus.REJECTED
    assert "max_positions_per_symbol" in second.message or "existing position" in second.message

def test_filled_entries_enforce_daily_limit_and_min_interval(tmp_path):
    db = str(tmp_path / "guard.sqlite3")
    g = ExecutionGuard(db, 10)
    fp1 = g.fingerprint("EURUSD", "2026-09-25T10:00:00Z", "BUY", "H4R-M5")
    assert g.claim("EURUSD", fp1, max_trades_per_day=1, min_minutes_between_trades=5).acquired
    g.release("EURUSD")
    g.record_filled("EURUSD")
    fp2 = g.fingerprint("EURUSD", "2026-09-25T10:05:00Z", "SELL", "H4R-M5")
    blocked = g.claim("EURUSD", fp2, max_trades_per_day=1, min_minutes_between_trades=5)
    assert not blocked.acquired
    assert "daily trade limit" in blocked.reason
