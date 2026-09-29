from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

import pandas as pd

from app.backtest.metrics import calculate_metrics
from app.config.models import AppConfig
from app.data.timeframes import timeframe_delta
from app.data.tick import Tick
from app.risk.position_sizer import SymbolSpec
from app.risk.risk_manager import RiskManager
from app.strategy.signal_engine import SignalEngine
from app.strategy.indicators import add_indicators
from app.utils.enums import Direction, Trend


@dataclass(frozen=True)
class BacktestResult:
    trades: pd.DataFrame
    metrics: dict[str, object]

    def to_csv(self, path: str | Path):
        self.trades.to_csv(path, index=False)

    def to_json(self, path: str | Path):
        Path(path).write_text(json.dumps(self.metrics, indent=2, default=str), encoding="utf-8")


class BacktestEngine:
    """Causal backtester with broker-realistic and research-unconstrained profiles."""

    def __init__(self, config: AppConfig, signal_engine: SignalEngine | None = None):
        self.config = config
        self.signal_engine = signal_engine or SignalEngine(config)
        self.risk_manager = RiskManager(config)
        self._window = 800

    def _closed_htf(self, htf_df: pd.DataFrame, decision_close: pd.Timestamp) -> pd.DataFrame:
        delta = timeframe_delta(self.config.higher_timeframe)
        idx = pd.DatetimeIndex(htf_df.index)
        closes = idx + delta
        mask = closes <= decision_close
        return htf_df.loc[mask].tail(self._window)

    def _classify_funnel(self, funnel: dict[str, int], decision, htf_ready: bool) -> None:
        funnel["candles_analyzed"] += 1
        if htf_ready and decision.context.trend is not Trend.NEUTRAL:
            funnel["htf_context_valid"] += 1
        structure = decision.context.structure
        if structure is not None and (structure.bullish or structure.bearish):
            funnel["structural_setups"] += 1
        if decision.context.breakout is not None:
            funnel["breakouts"] += 1
        if decision.context.retest is not None and decision.context.retest.detected:
            funnel["retests"] += 1
        pa = decision.context.price_action
        if pa is not None and pa.confirmed:
            funnel["price_action_confirmations"] += 1
            if decision.context.divergence is not None:
                funnel["indicator_confirmations"] += 1
        if decision.score.total >= self.config.strategy.minimum_confirmation_score:
            funnel["score_candidates"] += 1

    def _spec(self) -> SymbolSpec:
        b = self.config.backtest
        return SymbolSpec(
            self.config.point_size,
            b.tick_size,
            b.tick_value,
            b.contract_size,
            b.volume_min,
            b.volume_max,
            b.volume_step,
        )

    def _spread_price(self, row: pd.Series) -> float:
        value = float(row.get("spread", 0.0))
        # MT5 historical spread is expressed in points.
        return value * self.config.point_size

    def run(self, entry_df: pd.DataFrame, htf_df: pd.DataFrame,
            starting_equity: float | None = None, profile: str | None = None) -> BacktestResult:
        entry_df = add_indicators(entry_df.sort_index(), self.config.indicators)
        htf_df = add_indicators(htf_df.sort_index(), self.config.indicators)
        profile = (profile or self.config.backtest.profile).lower()
        if profile not in {"broker_realistic", "research_unconstrained"}:
            raise ValueError("profile must be broker_realistic or research_unconstrained")
        realistic = profile == "broker_realistic"
        equity = float(starting_equity if starting_equity is not None else (self.config.backtest.starting_equity if realistic else 10_000.0))
        initial_equity = equity
        spec = self._spec()
        max_positions = self.config.backtest.max_open_positions if realistic else 10**9
        next_available_idx = -1
        funnel: dict[str, int] = {
            "candles_analyzed": 0, "htf_context_valid": 0, "structural_setups": 0,
            "breakouts": 0, "retests": 0, "price_action_confirmations": 0,
            "indicator_confirmations": 0, "score_candidates": 0, "risk_accepted": 0,
            "executed_trades": 0, "insufficient_htf_history": 0, "invalid_entry_stop_side": 0,
            "margin_rejected": 0, "minimum_volume_rejected": 0, "overlap_blocked": 0,
        }
        records: list[dict[str, object]] = []
        active_exits: list[int] = []
        warmup_entry = max(self.config.indicators.ema_period, 60)
        min_htf = self.config.indicators.ema_period + 2

        for i in range(warmup_entry, len(entry_df) - 1):
            if realistic and i < next_available_idx:
                funnel["overlap_blocked"] += 1
                continue
            active_exits = [x for x in active_exits if x > i]
            if len(active_exits) >= max_positions:
                funnel["overlap_blocked"] += 1
                continue
            decision_close = pd.Timestamp(entry_df.index[i]) + timeframe_delta(self.config.entry_timeframe)
            closed_htf = self._closed_htf(htf_df, decision_close)
            if len(closed_htf) < min_htf:
                funnel["insufficient_htf_history"] += 1
                continue
            window = entry_df.iloc[max(0, i + 1 - self._window): i + 1]
            decision = self.signal_engine.evaluate(window, closed_htf, None)
            self._classify_funnel(funnel, decision, True)
            if not decision.accepted or decision.direction is Direction.FLAT:
                continue
            ctx = decision.context
            if ctx.retest is None or ctx.trendline is None:
                continue
            swings = [s for s in ctx.structure.points if s.confirmed]
            same = [s for s in swings if s.type.value == ("LOW" if decision.direction is Direction.BUY else "HIGH")]
            if not same:
                continue
            entry = float(entry_df.iloc[i + 1]["open"])
            swing = same[-1].price
            buffer = self.config.risk.sl_buffer_points * self.config.point_size
            sl = swing - buffer if decision.direction is Direction.BUY else swing + buffer
            stop_side_valid = (decision.direction is Direction.BUY and sl < entry) or (decision.direction is Direction.SELL and sl > entry)
            if not stop_side_valid:
                funnel["invalid_entry_stop_side"] += 1
                continue
            dist_points = abs(entry - sl) / self.config.point_size
            if dist_points <= 0 or dist_points > self.config.risk.max_sl_points:
                continue
            spread = self._spread_price(entry_df.iloc[i + 1])
            tick = Tick(pd.Timestamp(entry_df.index[i + 1]).to_pydatetime(), entry - spread / 2, entry + spread / 2)
            margin_per_lot = self.config.backtest.margin_per_lot
            if margin_per_lot is None:
                margin_per_lot = entry * spec.contract_size / self.config.backtest.leverage
            risk = self.risk_manager.assess(
                decision.direction, entry, sl, spec, equity, equity, tick,
                pd.Timestamp(entry_df.index[i + 1]).to_pydatetime(),
                margin_per_lot=margin_per_lot,
                free_margin=equity,
                risk_multiplier=1.0,
            )
            if not risk.accepted:
                if any("margin" in r.lower() for r in risk.reasons): funnel["margin_rejected"] += 1
                if any("minimum volume" in r.lower() for r in risk.reasons): funnel["minimum_volume_rejected"] += 1
                continue
            funnel["risk_accepted"] += 1
            tp = risk.tp
            exit_idx = None
            exit_price = None
            reason = None
            for j in range(i + 1, len(entry_df)):
                high, low = float(entry_df.iloc[j]["high"]), float(entry_df.iloc[j]["low"])
                if decision.direction is Direction.BUY:
                    if low <= sl:
                        exit_price, reason, exit_idx = sl, "SL", j; break
                    if high >= tp:
                        exit_price, reason, exit_idx = tp, "TP", j; break
                else:
                    if high >= sl:
                        exit_price, reason, exit_idx = sl, "SL", j; break
                    if low <= tp:
                        exit_price, reason, exit_idx = tp, "TP", j; break
            if exit_idx is None:
                continue
            pnl_price = exit_price - entry if decision.direction is Direction.BUY else entry - exit_price
            pnl_usd_gross = (pnl_price / spec.tick_size) * spec.tick_value * risk.volume
            slippage_usd = (self.config.backtest.slippage_points * spec.point_size / spec.tick_size) * spec.tick_value * risk.volume
            commission_usd = self.config.backtest.commission_per_lot * risk.volume
            pnl_usd = pnl_usd_gross - slippage_usd - commission_usd
            equity += pnl_usd
            active_exits.append(exit_idx)
            next_available_idx = exit_idx + 1 if realistic else -1
            records.append({
                "entry_time": entry_df.index[i + 1], "exit_time": entry_df.index[exit_idx],
                "direction": decision.direction.value, "entry": entry, "exit": exit_price,
                "pnl": pnl_usd, "pnl_usd": pnl_usd, "pnl_price": pnl_price,
                "pnl_pips": pnl_price / self.config.point_size / 10.0,
                "reason": reason, "bars_held": exit_idx - i - 1, "risk_money": risk.risk_money,
                "margin_required": risk.margin_required, "volume": risk.volume, "score": decision.score.total,
                "equity_after": equity, "commission_usd": commission_usd, "slippage_usd": slippage_usd,
                "profile": profile,
            })
            funnel["executed_trades"] += 1

        trades = pd.DataFrame(records)
        metrics = dict(calculate_metrics(trades, initial_equity))
        metrics.update({"funnel": funnel, "profile": profile, "starting_equity": initial_equity, "ending_equity": equity})
        return BacktestResult(trades, metrics)
