from __future__ import annotations

from dataclasses import dataclass, field

from app.execution.broker_interface import BrokerInterface
from app.risk.stop_manager import StopManager


@dataclass
class PositionManager:
    broker: BrokerInterface
    stop_manager: StopManager
    managed_initial_risk: dict[str, float] = field(default_factory=dict)

    def synchronize(self, symbol: str):
        return self.broker.get_positions(symbol)

    def manage_position(self, position, current_price: float, point_size: float):
        risk = self.managed_initial_risk.get(position.id, abs(position.entry_price - position.sl))
        update = self.stop_manager.update(position.id, position.direction, position.entry_price, current_price, position.sl, risk, point_size)
        if update.new_sl is not None:
            self.broker.modify_position(position.id, sl=update.new_sl)
        if update.close_percent > 0:
            self.broker.partial_close(position.id, position.volume * update.close_percent / 100.0)
        return update
