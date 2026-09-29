from __future__ import annotations

import os
from datetime import datetime, timezone

from app.data.tick import Tick
from app.execution.broker_interface import AccountInfo, BrokerInterface, OrderResult, Position
from app.risk.position_sizer import SymbolSpec
from app.utils.enums import Direction, OrderStatus


class MT5Broker(BrokerInterface):
    def __init__(self):
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise RuntimeError("MetaTrader5 package is required for live mode") from exc
        self.mt5 = mt5
        self.connected = False

    def connect(self):
        login = int(os.environ["MT5_LOGIN"])
        password = os.environ["MT5_PASSWORD"]
        server = os.environ["MT5_SERVER"]
        if not self.mt5.initialize(login=login, password=password, server=server):
            raise RuntimeError(f"MT5 initialize failed: {self.mt5.last_error()}")
        self.connected = True


    def validate_demo_account(self, expected_server: str = "MetaQuotes-Demo") -> tuple[bool, str]:
        info = self.mt5.account_info()
        if info is None:
            return False, f"account_info failed: {self.mt5.last_error()}"
        server = str(getattr(info, "server", "") or "")
        trade_mode = getattr(info, "trade_mode", None)
        demo_constant = getattr(self.mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
        if expected_server and server and server != expected_server:
            return False, f"Demo safeguard: connected server={server!r}, expected={expected_server!r}"
        if trade_mode is not None and int(trade_mode) != int(demo_constant):
            return False, f"Demo safeguard: account trade_mode={trade_mode}, expected demo={demo_constant}"
        return True, f"Demo account validated: server={server or expected_server}, trade_mode={trade_mode}"

    def disconnect(self):
        self.mt5.shutdown(); self.connected = False

    def get_account_info(self):
        info = self.mt5.account_info()
        if info is None: raise RuntimeError(f"account_info failed: {self.mt5.last_error()}")
        return AccountInfo(float(info.balance), float(info.equity), getattr(info, "currency", "USD"))

    def _ensure_symbol(self, symbol):
        if not self.mt5.symbol_select(symbol, True):
            raise RuntimeError(f"symbol_select failed for {symbol}: {self.mt5.last_error()}")

    def get_symbol_info(self, symbol):
        self._ensure_symbol(symbol)
        info = self.mt5.symbol_info(symbol)
        if info is None: raise RuntimeError(f"symbol_info failed: {symbol}")
        return SymbolSpec(float(info.point), float(info.trade_tick_size or info.point), float(info.trade_tick_value), float(info.trade_contract_size), float(info.volume_min), float(info.volume_max), float(info.volume_step), float(info.trade_stops_level), float(info.trade_freeze_level))

    def get_tick(self, symbol):
        self._ensure_symbol(symbol)
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None: raise RuntimeError(f"tick failed: {symbol}")
        return Tick(datetime.fromtimestamp(tick.time, tz=timezone.utc), float(tick.bid), float(tick.ask))

    def get_positions(self, symbol=None):
        rows = self.mt5.positions_get(symbol=symbol) if symbol else self.mt5.positions_get()
        rows = rows or []
        out=[]
        for r in rows:
            direction = Direction.BUY if r.type == self.mt5.POSITION_TYPE_BUY else Direction.SELL
            out.append(Position(str(r.ticket), r.symbol, direction, float(r.volume), float(r.price_open), float(r.sl), float(r.tp), datetime.fromtimestamp(r.time, tz=timezone.utc), str(r.magic)))
        return out

    def get_open_orders(self, symbol=None):
        return list(self.mt5.orders_get(symbol=symbol) or [])

    def _filling_mode(self, symbol: str):
        info = self.mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"symbol_info failed: {symbol}")
        mode = int(getattr(info, "filling_mode", 0))
        # MetaTrader bit flags: FOK=1, IOC=2. RETURN is the fallback.
        if mode & 1:
            return self.mt5.ORDER_FILLING_FOK
        if mode & 2:
            return self.mt5.ORDER_FILLING_IOC
        return self.mt5.ORDER_FILLING_RETURN

    def send_market_order(self, symbol, direction, volume, sl, tp, magic):
        tick = self.get_tick(symbol)
        order_type = self.mt5.ORDER_TYPE_BUY if direction is Direction.BUY else self.mt5.ORDER_TYPE_SELL
        price = tick.ask if direction is Direction.BUY else tick.bid
        request = {"action": self.mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": volume, "type": order_type, "price": price, "sl": sl, "tp": tp, "deviation": 20, "magic": int(abs(hash(magic)) % 2_000_000_000), "comment": magic, "type_time": self.mt5.ORDER_TIME_GTC, "type_filling": self._filling_mode(symbol)}
        result = self.mt5.order_send(request)
        if result is None: return OrderResult(OrderStatus.REJECTED, None, str(self.mt5.last_error()))
        status = OrderStatus.FILLED if result.retcode in {self.mt5.TRADE_RETCODE_DONE, self.mt5.TRADE_RETCODE_PLACED} else OrderStatus.REJECTED
        return OrderResult(status, str(result.order or result.deal) if result.order or result.deal else None, str(result.comment), float(result.price) if result.price else price)

    def modify_position(self, position_id, sl=None, tp=None):
        p = next((x for x in self.get_positions() if x.id == str(position_id)), None)
        if p is None: return OrderResult(OrderStatus.REJECTED, str(position_id), "position not found")
        request = {"action": self.mt5.TRADE_ACTION_SLTP, "symbol": p.symbol, "position": int(position_id), "sl": sl if sl is not None else p.sl, "tp": tp if tp is not None else p.tp}
        r = self.mt5.order_send(request)
        return OrderResult(OrderStatus.FILLED if r and r.retcode == self.mt5.TRADE_RETCODE_DONE else OrderStatus.REJECTED, str(position_id), str(getattr(r, "comment", "")))

    def close_position(self, position_id):
        p = next((x for x in self.get_positions() if x.id == str(position_id)), None)
        if p is None: return OrderResult(OrderStatus.REJECTED, str(position_id), "position not found")
        tick = self.get_tick(p.symbol)
        typ = self.mt5.ORDER_TYPE_SELL if p.direction is Direction.BUY else self.mt5.ORDER_TYPE_BUY
        price = tick.bid if p.direction is Direction.BUY else tick.ask
        req = {"action": self.mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": p.volume, "type": typ, "position": int(position_id), "price": price, "deviation": 20, "type_filling": self._filling_mode(p.symbol)}
        r = self.mt5.order_send(req)
        return OrderResult(OrderStatus.FILLED if r and r.retcode == self.mt5.TRADE_RETCODE_DONE else OrderStatus.REJECTED, str(position_id), str(getattr(r, "comment", "")))

    def partial_close(self, position_id, volume):
        p = next((x for x in self.get_positions() if x.id == str(position_id)), None)
        if p is None: return OrderResult(OrderStatus.REJECTED, str(position_id), "position not found")
        tick = self.get_tick(p.symbol)
        typ = self.mt5.ORDER_TYPE_SELL if p.direction is Direction.BUY else self.mt5.ORDER_TYPE_BUY
        price = tick.bid if p.direction is Direction.BUY else tick.ask
        req = {"action": self.mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": min(volume, p.volume), "type": typ, "position": int(position_id), "price": price, "deviation": 20, "type_filling": self._filling_mode(p.symbol)}
        r = self.mt5.order_send(req)
        return OrderResult(OrderStatus.FILLED if r and r.retcode == self.mt5.TRADE_RETCODE_DONE else OrderStatus.REJECTED, str(position_id), str(getattr(r, "comment", "")))

    def get_spread(self, symbol): return self.get_tick(symbol).spread
    def get_free_margin(self):
        info = self.mt5.account_info()
        return float(info.margin_free) if info is not None else None
    def get_margin_per_lot(self, symbol, price):
        self._ensure_symbol(symbol)
        info = self.mt5.symbol_info(symbol)
        if info is None: return None
        order_type = self.mt5.ORDER_TYPE_BUY
        value = self.mt5.order_calc_margin(order_type, symbol, 1.0, price)
        return float(value) if value is not None else None
    def get_capabilities(self, symbol):
        self._ensure_symbol(symbol)
        info = self.mt5.symbol_info(symbol)
        if info is None: raise RuntimeError(f"symbol_info failed: {symbol}")
        mode = int(getattr(info, "filling_mode", 0))
        filling = "FOK" if mode & 1 else "IOC" if mode & 2 else "RETURN"
        return {"symbol": symbol, "filling_mode": filling, "volume_min": float(info.volume_min), "volume_max": float(info.volume_max), "volume_step": float(info.volume_step), "tick_size": float(info.trade_tick_size or info.point), "tick_value": float(info.trade_tick_value), "contract_size": float(info.trade_contract_size)}

    def get_closed_deals(self, since: datetime) -> list[dict[str, object]]:
        start = since.astimezone(timezone.utc).replace(tzinfo=None) if since.tzinfo else since
        end = datetime.now(timezone.utc).replace(tzinfo=None)
        rows = self.mt5.history_deals_get(start, end) or []
        out = []
        entry_out = getattr(self.mt5, "DEAL_ENTRY_OUT", 1)
        for r in rows:
            if int(getattr(r, "entry", -1)) != int(entry_out):
                continue
            out.append({
                "deal_id": str(getattr(r, "ticket", "")),
                "position_id": str(getattr(r, "position_id", "")),
                "symbol": str(getattr(r, "symbol", "")),
                "magic": str(getattr(r, "magic", "")),
                "time": datetime.fromtimestamp(float(getattr(r, "time", 0)), tz=timezone.utc),
                "profit": float(getattr(r, "profit", 0.0)) + float(getattr(r, "swap", 0.0)) + float(getattr(r, "commission", 0.0)) + float(getattr(r, "fee", 0.0)),
                "reason": str(getattr(r, "comment", "")),
            })
        return out
    def is_market_open(self, symbol): return self.mt5.symbol_info(symbol).trade_mode != self.mt5.SYMBOL_TRADE_MODE_DISABLED
