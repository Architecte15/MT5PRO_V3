from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.data.tick import Tick
from app.execution.broker_interface import AccountInfo, BrokerInterface, OrderResult, Position
from app.risk.position_sizer import SymbolSpec
from app.utils.enums import Direction, OrderStatus


class MockBroker(BrokerInterface):
    def __init__(self, balance: float = 10_000.0, tick: Tick | None = None):
        self.account = AccountInfo(balance, balance)
        self.tick = tick or Tick(datetime.now(timezone.utc), 1.1, 1.1001)
        self.positions: dict[str, Position] = {}
        self.connected = False
        self.orders: list[OrderResult] = []
        self.symbol_specs = {}
        self.free_margin = balance

    def connect(self): self.connected = True
    def disconnect(self): self.connected = False
    def get_account_info(self): return self.account
    def get_symbol_info(self, symbol):
        return self.symbol_specs.get(symbol, SymbolSpec(0.00001, 0.00001, 1.0, 100000, 0.01, 100.0, 0.01))
    def get_tick(self, symbol): return self.tick
    def get_positions(self, symbol=None): return [p for p in self.positions.values() if symbol is None or p.symbol == symbol]
    def get_open_orders(self, symbol=None): return []
    def send_market_order(self, symbol, direction, volume, sl, tp, magic):
        pid = str(uuid4())
        price = self.tick.ask if direction is Direction.BUY else self.tick.bid
        pos = Position(pid, symbol, direction, volume, price, sl, tp, datetime.now(timezone.utc), magic)
        self.positions[pid] = pos
        res = OrderResult(OrderStatus.FILLED, pid, "mock fill", price)
        self.orders.append(res)
        return res
    def modify_position(self, position_id, sl=None, tp=None):
        p = self.positions[position_id]
        self.positions[position_id] = Position(p.id, p.symbol, p.direction, p.volume, p.entry_price, sl if sl is not None else p.sl, tp if tp is not None else p.tp, p.opened_at, p.magic)
        return OrderResult(OrderStatus.FILLED, position_id, "mock modify")
    def close_position(self, position_id):
        self.positions.pop(position_id, None)
        return OrderResult(OrderStatus.FILLED, position_id, "mock close")
    def partial_close(self, position_id, volume):
        p = self.positions[position_id]
        remaining = p.volume - volume
        if remaining <= 0:
            return self.close_position(position_id)
        self.positions[position_id] = Position(p.id, p.symbol, p.direction, remaining, p.entry_price, p.sl, p.tp, p.opened_at, p.magic)
        return OrderResult(OrderStatus.FILLED, position_id, "mock partial close")
    def get_spread(self, symbol): return self.tick.spread
    def is_market_open(self, symbol): return True
    def get_free_margin(self): return self.free_margin
    def get_margin_per_lot(self, symbol, price):
        spec = self.get_symbol_info(symbol)
        return price * spec.contract_size / 100.0
    def get_capabilities(self, symbol):
        spec = self.get_symbol_info(symbol)
        return {"symbol": symbol, "filling_mode": "MOCK", "volume_min": spec.volume_min, "volume_max": spec.volume_max, "volume_step": spec.volume_step, "tick_size": spec.tick_size, "tick_value": spec.tick_value, "contract_size": spec.contract_size}
