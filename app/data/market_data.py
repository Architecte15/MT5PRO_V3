from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.data.data_cache import DataCache
from app.data.tick import Tick
from app.utils.validation import validate_ohlc


class MarketDataError(RuntimeError):
    pass


class MarketDataProvider(ABC):
    @abstractmethod
    def get_candles(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def get_tick(self, symbol: str) -> Tick:
        raise NotImplementedError

    @abstractmethod
    def is_market_open(self, symbol: str) -> bool:
        raise NotImplementedError


@dataclass
class MockMarketDataProvider(MarketDataProvider):
    data: dict[tuple[str, str], pd.DataFrame]
    tick: Tick | None = None
    market_open: bool = True

    def get_candles(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        df = self.data.get((symbol, timeframe))
        if df is None:
            raise MarketDataError(f"No market data for {(symbol, timeframe)}")
        out = df.tail(limit).copy()
        errors = validate_ohlc(out)
        if errors:
            raise MarketDataError("; ".join(errors))
        return out

    def get_tick(self, symbol: str) -> Tick:
        if self.tick is None:
            now = datetime.now(timezone.utc)
            close = float(self.data[(symbol, next(iter(k[1] for k in self.data if k[0] == symbol)))]["close"].iloc[-1])
            return Tick(now, close, close)
        return self.tick

    def is_market_open(self, symbol: str) -> bool:
        return self.market_open


class CsvMarketDataProvider(MockMarketDataProvider):
    @classmethod
    def from_csv(cls, symbol: str, timeframe: str, path: str | Path) -> "CsvMarketDataProvider":
        df = pd.read_csv(path, parse_dates=[0])
        df = df.rename(columns={df.columns[0]: "timestamp"}).set_index("timestamp")
        return cls({(symbol, timeframe): df}, market_open=True)
