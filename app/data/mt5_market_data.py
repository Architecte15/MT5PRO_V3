from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.data.market_data import MarketDataProvider, MarketDataError
from app.data.tick import Tick


class MT5MarketDataProvider(MarketDataProvider):
    """Read-only market-data adapter; strategy code never imports MetaTrader5 directly."""

    TF_MAP = {
        "M1": "TIMEFRAME_M1", "M5": "TIMEFRAME_M5", "M15": "TIMEFRAME_M15",
        "M30": "TIMEFRAME_M30", "H1": "TIMEFRAME_H1", "H4": "TIMEFRAME_H4",
        "D1": "TIMEFRAME_D1", "W1": "TIMEFRAME_W1", "MN1": "TIMEFRAME_MN1",
    }

    def __init__(self, mt5):
        self.mt5 = mt5

    def _timeframe(self, timeframe: str):
        try:
            return getattr(self.mt5, self.TF_MAP[timeframe.upper()])
        except (KeyError, AttributeError) as exc:
            raise MarketDataError(f"Unsupported timeframe: {timeframe}") from exc

    @staticmethod
    def _normalize(rates) -> pd.DataFrame:
        if rates is None or len(rates) == 0:
            raise MarketDataError("MetaTrader 5 returned no rates")
        df = pd.DataFrame(rates)
        if "time" not in df.columns:
            raise MarketDataError("MT5 rates do not contain a time column")
        df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
        required = ["open", "high", "low", "close"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise MarketDataError(f"MT5 rates missing columns: {missing}")
        if "tick_volume" in df.columns:
            df["volume"] = df["tick_volume"]
        elif "real_volume" in df.columns:
            df["volume"] = df["real_volume"]
        else:
            df["volume"] = 0
        if "spread" not in df.columns:
            df["spread"] = 0
        out = df.set_index("timestamp")[
            ["open", "high", "low", "close", "volume", "spread"]
        ].sort_index()
        return out[~out.index.duplicated(keep="last")]

    def _ensure_symbol(self, symbol: str) -> None:
        if not self.mt5.symbol_select(symbol, True):
            raise MarketDataError(f"symbol_select failed for {symbol}: {self.mt5.last_error()}")

    def get_candles(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        self._ensure_symbol(symbol)
        rates = self.mt5.copy_rates_from_pos(symbol, self._timeframe(timeframe), 0, limit)
        try:
            return self._normalize(rates)
        except MarketDataError as exc:
            raise MarketDataError(f"No rates for {symbol} {timeframe}: {exc}; mt5={self.mt5.last_error()}") from exc

    def get_candles_range(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
        start = _as_utc(start)
        end = _as_utc(end)
        if end <= start:
            raise MarketDataError("End datetime must be after start datetime")
        self._ensure_symbol(symbol)
        rates = self.mt5.copy_rates_range(symbol, self._timeframe(timeframe), start, end)
        try:
            return self._normalize(rates)
        except MarketDataError as exc:
            raise MarketDataError(f"No range data for {symbol} {timeframe}: {exc}; mt5={self.mt5.last_error()}") from exc

    def get_tick(self, symbol: str) -> Tick:
        t = self.mt5.symbol_info_tick(symbol)
        if t is None:
            raise MarketDataError(f"No tick for {symbol}: {self.mt5.last_error()}")
        return Tick(datetime.fromtimestamp(t.time, tz=timezone.utc), float(t.bid), float(t.ask))

    def is_market_open(self, symbol: str) -> bool:
        info = self.mt5.symbol_info(symbol)
        return bool(info is not None and info.trade_mode != self.mt5.SYMBOL_TRADE_MODE_DISABLED)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
