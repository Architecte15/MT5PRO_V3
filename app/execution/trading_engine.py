from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.config.models import AppConfig
from app.data.market_data import MarketDataProvider
from app.execution.broker_interface import BrokerInterface, OrderResult
from app.execution.order_manager import OrderManager
from app.execution.execution_guard import ExecutionGuard
from app.execution.position_manager import PositionManager
from app.logging.logger import event
from app.risk.risk_manager import RiskManager, RiskAssessment
from app.risk.circuit_breaker import RiskCircuitBreaker
from app.strategy.signal_engine import SignalEngine, SignalDecision
from app.strategy.range_4h import detect_range_scalp_signals, RangeScalpSignal
from app.strategy.scoring import compute_score
from app.strategy.state_machine import StrategyContext
from app.strategy.adaptive_opportunity import scan as scan_adaptive_opportunity
from app.adaptive.learner import AdaptiveLearner, AdaptiveObservation
from app.utils.enums import Direction, OrderStatus


@dataclass(frozen=True)
class CycleResult:
    decision: SignalDecision
    risk: RiskAssessment | None
    order: OrderResult | None
    reason: str


class TradingEngine:
    def __init__(self, config: AppConfig, market_data: MarketDataProvider, broker: BrokerInterface, logger):
        self.config = config
        self.market_data = market_data
        self.broker = broker
        self.logger = logger
        self.signal_engine = SignalEngine(config)
        self.risk_manager = RiskManager(config)
        self.order_manager = OrderManager(
            broker, config.strategy_id,
            max_positions_per_symbol=config.execution.max_positions_per_symbol,
            allow_hedging=config.execution.allow_hedging,
            allow_opposite_entry=config.execution.allow_opposite_entry,
        )
        self.execution_guard = ExecutionGuard(config.execution.guard_db_path, config.execution.order_lock_timeout_seconds)
        from app.risk.stop_manager import StopManager
        self.position_manager = PositionManager(broker, StopManager(config.position_management))
        self._last_candle_timestamp = None
        self.circuit_breaker = RiskCircuitBreaker(
            config.risk.circuit_breaker_reduce_after_losses,
            config.risk.circuit_breaker_min_multiplier,
            config.risk.circuit_breaker_pause_after_losses,
            config.risk.circuit_breaker_cooldown_bars,
        )
        self._last_balance: float | None = None
        self.adaptive = AdaptiveLearner(
            config.adaptive_learning.memory_db_path,
            config.adaptive_learning.min_samples,
            config.adaptive_learning.min_lower_confidence,
            config.adaptive_learning.min_risk_multiplier,
            config.adaptive_learning.max_risk_multiplier,
        )
        self._history_scan_since = datetime.now(timezone.utc)

    def _is_new_closed_candle(self, frame) -> bool:
        if len(frame) < 2:
            return False
        # Last row can still be forming. Evaluate only the most recent CLOSED row (iloc[-2]).
        ts = frame.index[-2]
        if ts == self._last_candle_timestamp:
            return False
        self._last_candle_timestamp = ts
        return True

    def _latest_range_signal(self, entry, htf) -> RangeScalpSignal | None:
        cfg = self.config.four_hour_range
        if not cfg.enabled or not cfg.signal_gate_enabled or self.config.execution.live_strategy != "four_hour_range":
            return None
        try:
            signals = detect_range_scalp_signals(
                entry, htf,
                timezone=cfg.timezone,
                max_sl_points=cfg.max_sl_points,
                point_size=self.config.point_size,
                fallback_sl_enabled=cfg.fallback_sl_enabled,
                swing_strength=cfg.swing_strength,
                allow_multiple_per_day=cfg.allow_multiple_per_day,
            )
        except Exception as exc:
            event(self.logger, "ERROR", "H4 range evaluation failed", error=str(exc))
            return None
        if len(entry) < 2 or not signals:
            return None
        current_open_ts = entry.index[-1]
        candidates = [s for s in signals if s.entry_time == current_open_ts]
        return candidates[-1] if candidates else None

    def _range_decision(self, signal: RangeScalpSignal) -> SignalDecision:
        ctx = StrategyContext(self.config.symbol, self.config.entry_timeframe)
        score = compute_score(breakout=True, retest=True, htf_trend=True, price_action=True)
        return SignalDecision(signal.direction, True, f"H4R-M5 confirmed: {signal.reason}", score, ctx)

    def _adaptive_features_for_decision(self, decision: SignalDecision, entry, range_mode: bool) -> dict:
        last = entry.iloc[-2]
        lf = decision.context.liquidity_flow
        return {
            "direction": decision.direction.value,
            "regime": getattr(lf, "regime", decision.context.trend.value),
            "session": str(getattr(last.name, "hour", 0)),
            "trend_alignment": decision.context.trend.value,
            "pullback": "RANGE_REENTRY" if range_mode else "STRUCTURE_RETEST",
            "momentum": "CONFIRMED" if decision.score.total >= 7 else "MODERATE",
            "volatility": getattr(lf, "displacement_strength", "NORMAL"),
            "ema13_side": "ABOVE" if float(last.close) >= float(last.get("ema", last.close)) else "BELOW",
            "structure_bias": "BULLISH" if getattr(decision.context.structure, "bullish", False) else "BEARISH" if getattr(decision.context.structure, "bearish", False) else "MIXED",
        }

    def _resolve_adaptive_outcomes(self) -> None:
        if not self.config.adaptive_learning.enabled:
            return
        try:
            open_ids = {p.id for p in self.broker.get_positions(self.config.symbol)}
            pending = self.adaptive.pending()
            if not pending:
                return
            deals = self.broker.get_closed_deals(self._history_scan_since)
            self._history_scan_since = datetime.now(timezone.utc)
            grouped: dict[str, float] = {}
            latest: dict[str, object] = {}
            for d in deals:
                pid = str(d.get("position_id", ""))
                if pid:
                    grouped[pid] = grouped.get(pid, 0.0) + float(d.get("profit", 0.0) or 0.0)
                    latest[pid] = d
            for obs in pending:
                pid = obs["position_id"]
                if pid in open_ids:
                    continue
                if pid not in grouped:
                    continue
                d = latest[pid]
                self.adaptive.observe_outcome(pid, grouped[pid], d.get("time"), str(d.get("reason", "")))
                stats = self.adaptive.stats(obs["context_key"])
                event(self.logger, "ADAPT", "Trade outcome learned", position_id=pid, pnl=grouped[pid], context=obs["context_key"], samples=stats["samples"], win_rate=stats["win_rate"], lower_confidence=stats["lower_confidence"], risk_multiplier=self.adaptive.risk_multiplier(obs["context_key"]))
        except Exception as exc:
            event(self.logger, "ERROR", "Adaptive outcome resolution failed", error=str(exc))

    def _find_new_position_id(self, before_ids: set[str], symbol: str) -> str | None:
        for p in self.broker.get_positions(symbol):
            if p.id not in before_ids:
                return p.id
        return None

    def run_cycle(self) -> CycleResult | None:
        self._resolve_adaptive_outcomes()
        symbol = self.config.symbol
        account_snapshot = self.broker.get_account_info()
        if self._last_balance is not None:
            delta = account_snapshot.balance - self._last_balance
            if abs(delta) > 1e-12:
                self.circuit_breaker.on_trade(delta)
        self._last_balance = account_snapshot.balance
        self.circuit_breaker.on_new_bar()
        entry = self.market_data.get_candles(symbol, self.config.entry_timeframe, 800)
        htf = self.market_data.get_candles(symbol, self.config.higher_timeframe, 800)
        if not self._is_new_closed_candle(entry):
            return None
        if not self.market_data.is_market_open(symbol) or not self.broker.is_market_open(symbol):
            decision = self.signal_engine.evaluate(entry.iloc[:-1], htf, None)
            return CycleResult(decision, None, None, "market closed")
        range_signal = self._latest_range_signal(entry, htf)
        range_mode = range_signal is not None
        if range_signal is not None:
            decision = self._range_decision(range_signal)
            event(self.logger, "ENTRY", "H4R-M5 setup confirmed", direction=range_signal.direction.value, breakout=str(range_signal.breakout_time), reentry=str(range_signal.reentry_time), range_high=range_signal.range_high, range_low=range_signal.range_low, sl=range_signal.stop_loss, tp=range_signal.take_profit, fallback_sl=range_signal.used_fallback_sl)
        else:
            decision = self.signal_engine.evaluate(entry.iloc[:-1], htf.iloc[:-1], None)
            if (not decision.accepted and self.config.adaptive_learning.enabled and self.config.adaptive_learning.opportunity_scan_enabled):
                candidate = scan_adaptive_opportunity(entry.iloc[:-1], htf.iloc[:-1], self.config)
                if candidate is not None:
                    from app.strategy.scoring import compute_score
                    score = compute_score(htf_trend=True, price_action=True, breakout=True, retest=True)
                    decision = SignalDecision(candidate.direction, True, candidate.reason, score, candidate.context)
                    decision.context.reasons.append("ADAPTIVE_OPPORTUNITY")
                    decision.context.adaptive_features = candidate.features
        event(self.logger, "SCORE", f"{decision.reason}")
        if not decision.accepted:
            event(self.logger, "ENTRY", "NO TRADE", reason=decision.reason)
            return CycleResult(decision, None, None, decision.reason)
        existing = self.broker.get_positions(symbol)
        total_existing = self.broker.get_positions()
        if len(total_existing) >= self.config.execution.max_total_open_positions:
            reason = "max_total_open_positions reached"
            event(self.logger, "ENTRY", "BLOCKED", reason=reason, total_positions=len(total_existing), max_total=self.config.execution.max_total_open_positions)
            return CycleResult(decision, None, None, reason)
        max_positions = min(self.config.risk.max_open_positions, self.config.execution.max_positions_per_symbol)
        if len(existing) >= max_positions:
            reason = "max_open_positions reached"
            event(self.logger, "ENTRY", "BLOCKED", reason=reason, positions=len(existing), max_positions=max_positions)
            return CycleResult(decision, None, None, reason)
        if existing and not self.config.execution.allow_opposite_entry:
            reason = "existing position; new entry blocked"
            event(self.logger, "ENTRY", "BLOCKED", reason=reason, existing_direction=existing[0].direction.value)
            return CycleResult(decision, None, None, reason)
        ctx = decision.context
        tick = self.broker.get_tick(symbol)
        entry_price = tick.ask if decision.direction is Direction.BUY else tick.bid
        if range_mode:
            sl = float(range_signal.stop_loss)
        else:
            same = [s for s in ctx.structure.points if s.confirmed and s.type.value == ("LOW" if decision.direction is Direction.BUY else "HIGH")]
            if not same:
                reason = "No structural swing for SL"
                event(self.logger, "ENTRY", "BLOCKED", reason=reason)
                return CycleResult(decision, None, None, reason)
            sl, _ = self.risk_manager.build_stops(decision.direction, entry_price, same[-1].price)
        account = account_snapshot
        spec = self.broker.get_symbol_info(symbol)
        margin_per_lot = self.broker.get_margin_per_lot(symbol, entry_price)
        free_margin = self.broker.get_free_margin()
        adaptive_features = getattr(ctx, "adaptive_features", None) or self._adaptive_features_for_decision(decision, entry, range_mode)
        context_key = self.adaptive.context_key(adaptive_features)
        adaptive_allowed, adaptive_status = self.adaptive.opportunity_allowed(context_key, self.config.adaptive_learning.cold_start_allowed) if self.config.adaptive_learning.enabled else (True, {"status": "DISABLED"})
        if self.config.adaptive_learning.enabled and not adaptive_allowed:
            reason = f"Adaptive memory rejected weak context: {adaptive_status}"
            event(self.logger, "ADAPT", "ENTRY BLOCKED", reason=reason, context=context_key)
            return CycleResult(decision, None, None, reason)
        combined_multiplier = self.circuit_breaker.multiplier() * (self.adaptive.risk_multiplier(context_key) if self.config.adaptive_learning.enabled else 1.0)
        risk = self.risk_manager.assess(decision.direction, entry_price, sl, spec, account.balance, account.equity, tick, datetime.now(timezone.utc), margin_per_lot=margin_per_lot, free_margin=free_margin, risk_multiplier=combined_multiplier)
        event(self.logger, "RISK", "CAPABILITIES", capabilities=self.broker.get_capabilities(symbol), free_margin=free_margin, circuit_multiplier=self.circuit_breaker.multiplier(), adaptive_multiplier=self.adaptive.risk_multiplier(context_key) if self.config.adaptive_learning.enabled else 1.0, adaptive_status=adaptive_status.get("status"), adaptive_samples=adaptive_status.get("samples"))
        if not risk.accepted:
            reason = "; ".join(risk.reasons)
            event(self.logger, "ENTRY", "BLOCKED", reason=reason)
            return CycleResult(decision, risk, None, reason)

        closed_candle_ts = entry.index[-2]
        strategy_fingerprint_id = "H4R-M5" if range_mode else self.config.strategy_id
        fingerprint = self.execution_guard.fingerprint(symbol, closed_candle_ts, decision.direction.value, strategy_fingerprint_id)
        claim = self.execution_guard.claim(symbol, fingerprint, self.config.execution.max_trades_per_day, self.config.execution.min_minutes_between_trades)
        if not claim.acquired:
            reason = claim.reason
            event(self.logger, "ENTRY", "BLOCKED", reason=reason, fingerprint=fingerprint[:12])
            return CycleResult(decision, risk, None, reason)
        try:
            # Re-synchronize after claiming the cross-process symbol lock. Another
            # process may have filled the position between the first check and now.
            existing_after_lock = self.broker.get_positions(symbol)
            before_position_ids = {p.id for p in existing_after_lock}
            if existing_after_lock:
                reason = "position appeared before order send; entry cancelled"
                event(self.logger, "ENTRY", "BLOCKED", reason=reason, positions=len(existing_after_lock))
                return CycleResult(decision, risk, None, reason)
            order = self.order_manager.execute(symbol, decision.direction, risk.volume, risk.sl, risk.tp)
            if order.status is OrderStatus.FILLED:
                # Final broker synchronization closes the race window and makes the
                # execution state observable immediately to the next cycle/process.
                synced = self.broker.get_positions(symbol)
                self.execution_guard.record_filled(symbol)
                position_id = self._find_new_position_id(before_position_ids, symbol) or order.position_id
                if position_id and self.config.adaptive_learning.enabled:
                    self.adaptive.observe_entry(AdaptiveObservation(
                        position_id=str(position_id), symbol=symbol, direction=decision.direction.value,
                        strategy_id=strategy_fingerprint_id, context_key=context_key,
                        entry_time=str(closed_candle_ts), entry_price=float(entry_price), sl=float(risk.sl), tp=float(risk.tp), features=adaptive_features,
                    ))
                    event(self.logger, "ADAPT", "Trade context stored", position_id=str(position_id), context=context_key, model_version=self.config.adaptive_learning.model_version)
                self.execution_guard.set_cooldown(symbol, self.config.execution.signal_cooldown_seconds)
                event(self.logger, "ENTRY", f"{decision.direction.value} EXECUTED", volume=risk.volume, sl=risk.sl, tp=risk.tp, rr=risk.rr, positions_after=len(synced), cooldown_seconds=self.config.execution.signal_cooldown_seconds)
            else:
                event(self.logger, "ENTRY", "ORDER REJECTED", reason=order.message)
            return CycleResult(decision, risk, order, order.message)
        finally:
            self.execution_guard.release(symbol)
            self.execution_guard.purge_old_claims()

    def manage_positions(self) -> None:
        symbol = self.config.symbol
        tick = self.broker.get_tick(symbol)
        positions = self.broker.get_positions(symbol)
        for position in positions:
            current = tick.bid if position.direction is Direction.BUY else tick.ask
            self.position_manager.manage_position(position, current, self.config.point_size)
