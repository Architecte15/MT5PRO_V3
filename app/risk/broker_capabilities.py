from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrokerCapabilities:
    symbol: str
    filling_mode: str
    volume_min: float
    volume_max: float
    volume_step: float
    point_size: float
    tick_size: float
    tick_value: float
    contract_size: float
    leverage: float
    margin_per_lot: float | None = None

    def describe(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "filling_mode": self.filling_mode,
            "volume_min": self.volume_min,
            "volume_max": self.volume_max,
            "volume_step": self.volume_step,
            "point_size": self.point_size,
            "tick_size": self.tick_size,
            "tick_value": self.tick_value,
            "contract_size": self.contract_size,
            "leverage": self.leverage,
            "margin_per_lot": self.margin_per_lot,
        }
