#!/usr/bin/env python
"""
Live execution smoke test: sends N market orders on the connected MT5 account,
verifies fill + SL/TP, modifies stops, closes each position, reports results.

Usage:
    python -m scripts.test_execution --orders 10 --volume 0.01 --symbol EURUSD

Sequential mode is chosen automatically when free margin cannot hold all
orders at once (sends one, verifies, closes, then the next).
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MT5 execution smoke test")
    p.add_argument("--orders", type=int, default=10, help="Number of orders to send")
    p.add_argument("--volume", type=float, default=0.01, help="Lot size per order")
    p.add_argument("--symbol", default="EURUSD", help="Symbol")
    p.add_argument("--sl-points", type=float, default=50, help="Initial SL distance in points")
    p.add_argument("--rr", type=float, default=2.0, help="Reward:risk ratio for TP")
    p.add_argument("--env-file", default=".env")
    p.add_argument("--live-ack", action="store_true",
                   help="Required to run against a server whose name has no 'demo'")
    return p.parse_args()


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

    print(f"Connecting: login={login} server={server}")
    if not mt5.initialize(login=login, password=password, server=server):
        print(f"ERROR: initialize failed {mt5.last_error()}", file=sys.stderr)
        return 1

    results: list[dict] = []
    try:
        acc = mt5.account_info()
        if acc is None:
            print("ERROR: account_info failed", file=sys.stderr)
            return 1
        print(f"Account: {acc.login} | server={acc.server} | balance={acc.balance:.2f} {acc.currency}")
        if "demo" not in (acc.server or "").lower() and not args.live_ack:
            print("ERROR: server name does not contain 'demo'; looks like a REAL account.",
                  file=sys.stderr)
            print("Re-run with --live-ack if you really want to trade it.", file=sys.stderr)
            return 1

        if not mt5.symbol_select(args.symbol, True):
            print(f"ERROR: cannot select {args.symbol}: {mt5.last_error()}", file=sys.stderr)
            return 1

        info = mt5.symbol_info(args.symbol)
        tick = mt5.symbol_info_tick(args.symbol)
        if info is None or tick is None:
            print(f"ERROR: symbol/tick unavailable: {mt5.last_error()}", file=sys.stderr)
            return 1

        point = float(info.point)
        stops_level = float(info.trade_stops_level)
        vol_step = float(info.volume_step)
        vol_min = float(info.volume_min)

        volume = max(round(args.volume / vol_step) * vol_step, vol_min)
        sl_dist = max(args.sl_points * point, (stops_level + 5) * point)

        # Native MT5 tick has no .spread; compute it.
        spread_pts = (float(tick.ask) - float(tick.bid)) / point

        # Symbol-specific filling mode (bitmask: 1=FOK, 2=IOC); fallback RETURN.
        mask = int(getattr(info, "filling_mode", 0))
        if mask & 1:
            filling = mt5.ORDER_FILLING_FOK
        elif mask & 2:
            filling = mt5.ORDER_FILLING_IOC
        else:
            filling = mt5.ORDER_FILLING_RETURN

        # Margin per order (API first, manual formula as fallback).
        try:
            mres = mt5.order_calc_margin(
                True, args.symbol, mt5.ORDER_TYPE_BUY, volume, float(tick.ask))
            margin_one = float(mres.margin) if mres is not None else 0.0
        except Exception:
            margin_one = 0.0
        if margin_one <= 0:
            margin_one = (float(info.trade_contract_size) * volume
                          * float(tick.ask) / max(int(acc.leverage), 1))
        free = float(mt5.account_info().margin_free)
        max_parallel = int(free // margin_one) if margin_one > 0 else 0
        sequential = args.orders > max_parallel

        print(f"Symbol: {args.symbol} point={point} stops_level={stops_level} "
              f"volume={volume} spread={spread_pts:.1f}pts filling={'FOK' if mask & 1 else ('IOC' if mask & 2 else 'RETURN')}")
        print(f"Margin/order: {margin_one:.2f} | free: {free:.2f} | max parallel: {max_parallel}")
        print(f"Mode: {'SEQUENTIAL (1 at a time)' if sequential else f'PARALLEL ({args.orders})'}")
        print(f"Sending {args.orders} orders...\n")

        t0 = time.time()

        def close_position(pos, attempts: int = 3) -> bool:
            """Close at market, accepting the realized P&L. Network blips
            (retcode 10031) are retried instead of abandoning the position."""
            for k in range(attempts):
                tick = mt5.symbol_info_tick(pos.symbol)
                ctype = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
                cprice = float(tick.bid) if pos.type == mt5.POSITION_TYPE_BUY else float(tick.ask)
                cres = mt5.order_send({
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": pos.symbol,
                    "volume": pos.volume,
                    "type": ctype,
                    "position": pos.ticket,
                    "price": cprice,
                    "deviation": 50,
                    "type_filling": filling,
                })
                if cres and cres.retcode == mt5.TRADE_RETCODE_DONE:
                    return True
                if k < attempts - 1:
                    time.sleep(0.5)
            return False

        for i in range(1, args.orders + 1):
            tick = mt5.symbol_info_tick(args.symbol)
            buy = (i % 2) == 1  # Alternate BUY / SELL to exercise both paths
            if buy:
                price = float(tick.ask)
                sl = price - sl_dist
                tp = price + sl_dist * args.rr
                otype = mt5.ORDER_TYPE_BUY
            else:
                price = float(tick.bid)
                sl = price + sl_dist
                tp = price - sl_dist * args.rr
                otype = mt5.ORDER_TYPE_SELL

            res = mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": args.symbol,
                "volume": volume,
                "type": otype,
                "price": price,
                "sl": round(sl, info.digits),
                "tp": round(tp, info.digits),
                "deviation": 20,
                "magic": 424242,
                "comment": f"pytest{i}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling,
            })
            row = {
                "n": i, "side": "BUY" if buy else "SELL",
                "send_ok": False, "retcode": None, "position_id": None,
                "fill_price": None, "sl_ok": False, "tp_ok": False,
                "modify_ok": None, "close_ok": None, "error": "",
            }
            if res is None:
                row["error"] = f"order_send None: {mt5.last_error()}"
                results.append(row)
                print(f"[{i:02d}] {row['side']} FAILED (None) {row['error']}")
                continue

            row["retcode"] = res.retcode
            row["position_id"] = res.order or res.deal or None
            row["fill_price"] = float(res.price) if res.price else None
            row["send_ok"] = res.retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED)
            if not row["send_ok"]:
                row["error"] = f"retcode={res.retcode} comment={res.comment}"
                results.append(row)
                print(f"[{i:02d}] {row['side']} REJECTED {row['error']}")
                continue

            # Verify position exists with SL/TP
            pos = None
            for _ in range(5):
                positions = [p for p in (mt5.positions_get(symbol=args.symbol) or [])
                             if p.magic == 424242]
                if positions:
                    pos = next((p for p in positions if p.ticket == res.order), positions[-1])
                    if pos.sl != 0 and pos.tp != 0:
                        break
                time.sleep(0.2)
            if pos is None:
                row["error"] = "position not found after fill"
                results.append(row)
                print(f"[{i:02d}] {row['side']} FILLED but position not found")
                continue

            row["position_id"] = pos.ticket
            row["fill_price"] = float(pos.price_open)
            row["sl_ok"] = pos.sl != 0
            row["tp_ok"] = pos.tp != 0

            # Modify SL by +5 points in favor (stop-move smoke test)
            move = 5 * point
            new_sl = (pos.sl + move) if buy else (pos.sl - move)
            mres2 = mt5.order_send({
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": args.symbol,
                "position": pos.ticket,
                "sl": round(new_sl, info.digits),
                "tp": pos.tp,
            })
            row["modify_ok"] = bool(mres2 and mres2.retcode == mt5.TRADE_RETCODE_DONE)
            if not row["modify_ok"]:
                row["error"] += f" modify_failed={getattr(mres2, 'comment', mt5.last_error())}"

            # Sequential: close before sending the next one
            if sequential:
                row["close_ok"] = close_position(pos)

            results.append(row)
            print(f"[{i:02d}] {row['side']} ticket={row['position_id']} "
                  f"fill={row['fill_price']} sl_ok={row['sl_ok']} tp_ok={row['tp_ok']} "
                  f"modify_ok={row['modify_ok']} close_ok={row['close_ok']}")

        elapsed = time.time() - t0

        # Close anything left over
        leftover = [p for p in (mt5.positions_get(symbol=args.symbol) or [])
                    if p.magic == 424242]
        if leftover:
            print("\nClosing remaining test positions...")
            for p in leftover:
                ok = close_position(p, attempts=5)
                match = next((r for r in results if r["position_id"] == p.ticket), None)
                if match:
                    match["close_ok"] = ok
                print(f"  close ticket={p.ticket} ok={ok}")

        still_open = [p for p in (mt5.positions_get(symbol=args.symbol) or [])
                      if p.magic == 424242]
        sent = len(results)
        filled = sum(1 for r in results if r["send_ok"])
        sl_tp_ok = sum(1 for r in results if r["sl_ok"] and r["tp_ok"])
        modified = sum(1 for r in results if r["modify_ok"])
        closed = sum(1 for r in results if r["close_ok"])
        avg_ms = (elapsed / max(sent, 1)) * 1000

        print("\n" + "=" * 52)
        print("EXECUTION TEST REPORT")
        print("=" * 52)
        print(f"Orders sent        : {sent}")
        print(f"Filled             : {filled}/{sent}")
        print(f"SL+TP attached     : {sl_tp_ok}/{sent}")
        print(f"Stop modified      : {modified}/{sent}")
        print(f"Closed             : {closed}/{sent}")
        print(f"Positions remaining: {len(still_open)}")
        print(f"Avg round-trip     : {avg_ms:.0f} ms/order")
        print(f"Account balance    : {mt5.account_info().balance:.2f}")
        print("=" * 52)

        failures = [r for r in results if not r["send_ok"] or not r["sl_ok"] or not r["tp_ok"]]
        if failures:
            print(f"\n{len(failures)} order(s) with problems:")
            for r in failures:
                print(f"  #{r['n']} {r['side']} retcode={r['retcode']} "
                      f"sl_ok={r['sl_ok']} tp_ok={r['tp_ok']} err={r['error']}")

        return 0 if filled == sent and sl_tp_ok == sent and not still_open else 2

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    sys.exit(main())
