from __future__ import annotations

from dataclasses import dataclass

from app.execution.broker_interface import BrokerInterface, OrderResult
from app.utils.enums import Direction, OrderStatus


@dataclass
class OrderManager:
    broker: BrokerInterface
    magic: str
    max_positions_per_symbol: int = 1
    allow_hedging: bool = False
    allow_opposite_entry: bool = False

    def execute(self, symbol: str, direction: Direction, volume: float, sl: float, tp: float) -> OrderResult:
        if volume <= 0:
            return OrderResult(OrderStatus.REJECTED, None, "volume <= 0")
        if direction not in (Direction.BUY, Direction.SELL):
            return OrderResult(OrderStatus.REJECTED, None, "invalid direction")
        positions = self.broker.get_positions(symbol)
        if len(positions) >= self.max_positions_per_symbol:
            return OrderResult(OrderStatus.REJECTED, None, "max_positions_per_symbol reached")
        if not self.allow_hedging and positions:
            if any(p.direction is not direction for p in positions):
                return OrderResult(OrderStatus.REJECTED, None, "opposite position exists; hedging disabled")
            if not self.allow_opposite_entry:
                return OrderResult(OrderStatus.REJECTED, None, "existing position; duplicate entry blocked")
        return self.broker.send_market_order(symbol, direction, volume, sl, tp, self.magic)
