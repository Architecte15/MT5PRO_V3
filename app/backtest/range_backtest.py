from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pandas as pd

from app.backtest.metrics import calculate_metrics
from app.strategy.range_4h import detect_range_scalp_signals
from app.utils.enums import Direction


def run_range_backtest(
    m5_df: pd.DataFrame,
    h4_df: pd.DataFrame,
    *,
    starting_equity: float = 17.65,
    volume: float = 0.01,
    point_size: float = 0.00001,
    tick_size: float = 0.00001,
    tick_value: float = 1.0,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    max_sl_points: float = 500.0,
    timezone: str = "America/New_York",
    fallback_sl_enabled: bool = True,
    allow_multiple_per_day: bool = True,
) -> tuple[pd.DataFrame, dict[str, object]]:
    signals = detect_range_scalp_signals(
        m5_df,
        h4_df,
        timezone=timezone,
        max_sl_points=max_sl_points,
        point_size=point_size,
        fallback_sl_enabled=fallback_sl_enabled,
        allow_multiple_per_day=allow_multiple_per_day,
    )
    m5 = m5_df.copy().sort_index()
    if m5.index.tz is None:
        m5.index = m5.index.tz_localize("UTC")
    else:
        m5.index = m5.index.tz_convert("UTC")
    records: list[dict[str, object]] = []
    equity = float(starting_equity)
    for signal in signals:
        try:
            entry_idx = m5.index.get_loc(signal.entry_time)
        except KeyError:
            continue
        exit_idx = None
        exit_price = None
        reason = None
        for j in range(entry_idx, len(m5)):
            row = m5.iloc[j]
            high, low = float(row.high), float(row.low)
            if signal.direction is Direction.BUY:
                if low <= signal.stop_loss:
                    exit_idx, exit_price, reason = j, signal.stop_loss, "SL"; break
                if high >= signal.take_profit:
                    exit_idx, exit_price, reason = j, signal.take_profit, "TP"; break
            else:
                if high >= signal.stop_loss:
                    exit_idx, exit_price, reason = j, signal.stop_loss, "SL"; break
                if low <= signal.take_profit:
                    exit_idx, exit_price, reason = j, signal.take_profit, "TP"; break
        if exit_idx is None:
            continue
        pnl_price = exit_price - signal.entry_price if signal.direction is Direction.BUY else signal.entry_price - exit_price
        pnl_usd = (pnl_price / tick_size) * tick_value * volume
        pnl_usd -= (slippage_points * point_size / tick_size) * tick_value * volume
        commission_usd = commission_per_lot * volume
        pnl_usd -= commission_usd
        equity += pnl_usd
        records.append({
            **asdict(signal),
            "direction": signal.direction.value,
            "exit_time": m5.index[exit_idx],
            "exit_price": exit_price,
            "reason_exit": reason,
            "pnl_price": pnl_price,
            "pnl_pips": pnl_price / point_size / 10.0,
            "pnl_usd": pnl_usd,
            "pnl": pnl_usd,
            "risk_money": abs(signal.entry_price - signal.stop_loss) / tick_size * tick_value * volume,
            "volume": volume,
            "bars_held": exit_idx - entry_idx,
            "equity_after": equity,
        })
    trades = pd.DataFrame(records)
    metrics = calculate_metrics(trades, starting_equity)
    metrics.update({
        "strategy": "FIRST_H4_RANGE_REENTRY_M5",
        "timezone": timezone,
        "rr": 2.0,
        "signals_detected": len(signals),
        "fallback_sl_count": sum(s.used_fallback_sl for s in signals),
    })
    return trades, metrics
