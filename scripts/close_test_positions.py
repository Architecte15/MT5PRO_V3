#!/usr/bin/env python
"""Close leftover smoke-test positions (magic 424242) on the MT5 account.

A network blip (retcode 10031) can leave test positions open: the send, the
close, and the final cleanup all fail at once. This script retries until the
account is clean, closing at market price and accepting whatever P&L the
market gives (a realized loss beats an abandoned open position).

Usage:
    python -m scripts.close_test_positions [--symbol EURUSD]
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from dotenv import load_dotenv

MAGIC = 424242
MAX_ATTEMPTS = 10


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Close leftover test positions")
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--env-file", default=".env")
    return p.parse_args()


def _filling_mode(mt5, symbol: str) -> int:
    info = mt5.symbol_info(symbol)
    mask = int(getattr(info, "filling_mode", 0)) if info is not None else 0
    if mask & 1:
        return mt5.ORDER_FILLING_FOK
    if mask & 2:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def _close_one(mt5, pos) -> tuple[bool, str]:
    tick = mt5.symbol_info_tick(pos.symbol)
    if tick is None:
        return False, f"no tick: {mt5.last_error()}"
    is_buy = pos.type == mt5.POSITION_TYPE_BUY
    res = mt5.order_send({
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
        "position": pos.ticket,
        "price": float(tick.bid) if is_buy else float(tick.ask),
        "deviation": 50,
        "magic": MAGIC,
        "comment": "cleanup",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": _filling_mode(mt5, pos.symbol),
    })
    if res is None:
        return False, f"order_send None: {mt5.last_error()}"
    if res.retcode != mt5.TRADE_RETCODE_DONE:
        return False, f"retcode={res.retcode} {res.comment}"
    return True, ""


def _realized_profit(mt5, position_ticket: int) -> float | None:
    try:
        deals = mt5.history_deals_get(position=position_ticket) or ()
    except Exception:
        return None
    profits = [float(d.profit) for d in deals if d.position_id == position_ticket]
    return sum(profits) if profits else None


def main() -> int:
    args = parse_args()
    load_dotenv(args.env_file, override=False)

    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("ERROR: pip install MetaTrader5", file=sys.stderr)
        return 1

    login = int(os.environ.get("MT5_LOGIN", 0))
    password = os.environ.get("MT5_PASSWORD", "")
    server = os.environ.get("MT5_SERVER", "")
    if not (login and password and server):
        print("ERROR: MT5_LOGIN / MT5_PASSWORD / MT5_SERVER missing in .env", file=sys.stderr)
        return 1

    if not mt5.initialize(login=login, password=password, server=server):
        print(f"ERROR: initialize failed {mt5.last_error()}", file=sys.stderr)
        return 1

    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            positions = [p for p in (mt5.positions_get(symbol=args.symbol) or [])
                         if p.magic == MAGIC]
            if not positions:
                acc = mt5.account_info()
                print("\nAccount clean: no test positions left.")
                print(f"Balance: {acc.balance:.2f} {acc.currency} | Equity: {acc.equity:.2f}")
                return 0

            if attempt == 1:
                print(f"{len(positions)} leftover test position(s):")
                for p in positions:
                    side = "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL"
                    print(f"  ticket={p.ticket} {side} vol={p.volume} open={p.price_open} "
                          f"sl={p.sl} tp={p.tp} floating={p.profit:.2f}")

            for p in positions:
                ok, err = _close_one(mt5, p)
                if ok:
                    realized = _realized_profit(mt5, p.ticket)
                    extra = f" realized={realized:+.2f}" if realized is not None else ""
                    print(f"  [attempt {attempt}] close ticket={p.ticket} OK{extra}")
                else:
                    print(f"  [attempt {attempt}] close ticket={p.ticket} FAILED: {err}")
            time.sleep(1.0)

        remaining = [p for p in (mt5.positions_get(symbol=args.symbol) or [])
                     if p.magic == MAGIC]
        if remaining:
            print(f"ERROR: {len(remaining)} position(s) still open after {MAX_ATTEMPTS} attempts",
                  file=sys.stderr)
            return 2
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    sys.exit(main())
