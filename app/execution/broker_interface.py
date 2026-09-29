from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.data.tick import Tick
from app.risk.position_sizer import SymbolSpec
from app.utils.enums import Direction, OrderStatus


@dataclass(frozen=True)
class AccountInfo:
    balance: float
    equity: float
    currency: str = "USD"


@dataclass(frozen=True)
class Position:
    id: str
    symbol: str
    direction: Direction
    volume: float
    entry_price: float
    sl: float
    tp: float
    opened_at: datetime
    magic: str = ""


@dataclass(frozen=True)
class OrderResult:
    status: OrderStatus
    position_id: str | None
    message: str
    fill_price: float | None = None


class BrokerInterface(ABC):
    @abstractmethod
    def connect(self) -> None: ...
    @abstractmethod
    def disconnect(self) -> None: ...
    @abstractmethod
    def get_account_info(self) -> AccountInfo: ...
    @abstractmethod
    def get_symbol_info(self, symbol: str) -> SymbolSpec: ...
    @abstractmethod
    def get_tick(self, symbol: str) -> Tick: ...
    @abstractmethod
    def get_positions(self, symbol: str | None = None) -> list[Position]: ...
    @abstractmethod
    def get_open_orders(self, symbol: str | None = None) -> list[Any]: ...
    @abstractmethod
    def send_market_order(self, symbol: str, direction: Direction, volume: float, sl: float, tp: float, magic: str) -> OrderResult: ...
    @abstractmethod
    def modify_position(self, position_id: str, sl: float | None = None, tp: float | None = None) -> OrderResult: ...
    @abstractmethod
    def close_position(self, position_id: str) -> OrderResult: ...
    @abstractmethod
    def partial_close(self, position_id: str, volume: float) -> OrderResult: ...
    @abstractmethod
    def get_spread(self, symbol: str) -> float: ...
    @abstractmethod
    def is_market_open(self, symbol: str) -> bool: ...

    def get_free_margin(self) -> float | None:
        info = self.get_account_info()
        return None

    def get_margin_per_lot(self, symbol: str, price: float) -> float | None:
        return None

    def get_capabilities(self, symbol: str) -> dict[str, object]:
        spec = self.get_symbol_info(symbol)
        return {"symbol": symbol, "volume_min": spec.volume_min, "volume_max": spec.volume_max, "volume_step": spec.volume_step}

    def get_closed_deals(self, since: datetime) -> list[dict[str, object]]:
        """Return closed deals for outcome learning when the broker supports history."""
        return []
