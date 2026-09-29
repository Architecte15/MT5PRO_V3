from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from app.config.models import AppConfig
from app.strategy.divergence import rsi_divergence
from app.strategy.indicators import add_indicators, has_squeeze_before
from app.strategy.market_structure import classify_structure, detect_swings
from app.strategy.price_action import analyze_price_action
from app.strategy.scoring import SignalScore, compute_score
from app.strategy.state_machine import StrategyContext, StrategyStateMachine
from app.strategy.trendline import build_trendline
from app.strategy.liquidity_flow.model import build_features
from app.strategy.breakout import detect_breakout
from app.strategy.retest import detect_retest
from app.utils.enums import Direction, StrategyState, Trend


@dataclass(frozen=True)
class SignalDecision:
    direction: Direction
    accepted: bool
    reason: str
    score: SignalScore
    context: StrategyContext


class SignalEngine:
    def __init__(self, config: AppConfig):
        self.config = config

    def evaluate(self, entry_df: pd.DataFrame, htf_df: pd.DataFrame, direction: Direction | None = None) -> SignalDecision:
        cfg = self.config
        if len(entry_df) < max(cfg.indicators.ema_period, 50):
            empty = compute_score()
            ctx = StrategyContext(cfg.symbol, cfg.entry_timeframe)
            return SignalDecision(Direction.FLAT, False, "Insufficient data", empty, ctx)
        entry = add_indicators(entry_df, cfg.indicators)
        htf = add_indicators(htf_df, cfg.indicators)
        htf_last = htf.iloc[-1]
        htf_prev = htf.iloc[-2]
        htf_trend = Trend.NEUTRAL
        if htf_last["close"] > htf_last["ema"] and htf_last["ema"] > htf_prev["ema"]:
            htf_trend = Trend.BULLISH
        elif htf_last["close"] < htf_last["ema"] and htf_last["ema"] < htf_prev["ema"]:
            htf_trend = Trend.BEARISH
        swings = detect_swings(entry, cfg.strategy.swing_strength)
        structure = classify_structure(swings)
        desired = direction
        if desired is None:
            desired = Direction.BUY if htf_trend is Trend.BULLISH and structure.bullish else Direction.SELL if htf_trend is Trend.BEARISH and structure.bearish else Direction.FLAT
        ctx = StrategyContext(cfg.symbol, cfg.entry_timeframe, trend=htf_trend, structure=structure)
        if cfg.liquidity_flow.enabled:
            lf, _, _, _ = build_features(entry, cfg.entry_timeframe, cfg.indicators, cfg.liquidity_flow.swing_strength, cfg.liquidity_flow.zone_tolerance_points * cfg.point_size)
            ctx.liquidity_flow = lf
        sm = StrategyStateMachine(ctx)
        now = datetime.now(timezone.utc)
        if desired is Direction.FLAT:
            return SignalDecision(Direction.FLAT, False, "No compatible trend/structure", compute_score(htf_trend=False, structure=False), ctx)
        sm.transition(StrategyState.TREND_DETECTED, f"HTF={htf_trend.value}", now)
        compatible = (desired is Direction.BUY and htf_trend is Trend.BULLISH and structure.bullish) or (desired is Direction.SELL and htf_trend is Trend.BEARISH and structure.bearish)
        if not compatible and not cfg.strategy.allow_counter_trend_trades:
            return SignalDecision(desired, False, "HTF/structure incompatible", compute_score(htf_trend=False, structure=False), ctx)
        trendline = build_trendline(swings, desired)
        ctx.trendline = trendline
        if trendline is None:
            return SignalDecision(desired, False, "No valid trendline", compute_score(htf_trend=compatible, trendline=False), ctx)
        breakout = detect_breakout(entry, trendline, desired, cfg.strategy.breakout_buffer_points, cfg.point_size, cfg.strategy.max_retest_bars + 1)
        ctx.breakout = breakout
        if breakout is None:
            return SignalDecision(desired, False, "No confirmed breakout", compute_score(htf_trend=compatible, trendline=True, breakout=False), ctx)
        sm.transition(StrategyState.BREAKOUT_DETECTED, "Breakout confirmed on closed candle", now)
        sm.transition(StrategyState.WAITING_RETEST, "Retest required", now)
        retest = detect_retest(entry, desired, breakout.level, cfg.strategy.retest_tolerance_points, cfg.point_size, cfg.strategy.max_retest_bars, breakout.index)
        ctx.retest = retest
        if not retest.detected:
            return SignalDecision(desired, False, f"No retest: {retest.reason}", compute_score(htf_trend=compatible, breakout=True, retest=False), ctx)
        sm.transition(StrategyState.RETEST_CONFIRMED, "Retest confirmed", now)
        sm.transition(StrategyState.WAITING_CONFIRMATION, "Awaiting price action confirmation", now)
        pa = analyze_price_action(entry, desired, cfg.indicators.momentum_factor, cfg.indicators.wick_ratio)
        ctx.price_action = pa
        if not pa.confirmed:
            return SignalDecision(desired, False, "Price action confirmation missing", compute_score(htf_trend=compatible, breakout=True, retest=True, price_action=False), ctx)
        sm.transition(StrategyState.INDICATOR_VALIDATION, "Price action confirmed", now)
        div = rsi_divergence(entry, swings, cfg.indicators.divergence_lookback)
        ctx.divergence = div
        last = entry.iloc[-1]
        bb_fav = float(last["low"]) <= float(last["bb_lower"]) if desired is Direction.BUY else float(last["high"]) >= float(last["bb_upper"])
        rsi_fav = float(last["rsi"]) < cfg.indicators.rsi_oversold or div.bullish if desired is Direction.BUY else float(last["rsi"]) > cfg.indicators.rsi_overbought or div.bearish
        macd_bull = float(entry["macd_main"].iloc[-2]) <= float(entry["macd_signal"].iloc[-2]) and float(last["macd_main"]) > float(last["macd_signal"])
        macd_bear = float(entry["macd_main"].iloc[-2]) >= float(entry["macd_signal"].iloc[-2]) and float(last["macd_main"]) < float(last["macd_signal"])
        macd_cross = macd_bull if desired is Direction.BUY else macd_bear
        hist_fav = float(last["macd_hist"]) > float(entry["macd_hist"].iloc[-2]) if desired is Direction.BUY else float(last["macd_hist"]) < float(entry["macd_hist"].iloc[-2])
        macd_zero = float(last["macd_main"]) <= 0 if desired is Direction.BUY else float(last["macd_main"]) >= 0
        squeeze = has_squeeze_before(entry["bb_width"].iloc[:-1], cfg.indicators.squeeze_lookback, cfg.indicators.squeeze_threshold, cfg.indicators.minimum_squeeze_candles)
        score = compute_score(htf_trend=compatible, breakout=True, retest=True, engulfing=(pa.bullish_engulfing if desired is Direction.BUY else pa.bearish_engulfing), momentum_candle=pa.momentum_candle, wick_rejection=pa.wick_rejection, bollinger_extreme=bb_fav, rsi_extreme=(float(last["rsi"]) < cfg.indicators.rsi_oversold if desired is Direction.BUY else float(last["rsi"]) > cfg.indicators.rsi_overbought), rsi_divergence=(div.bullish if desired is Direction.BUY else div.bearish), macd_crossover=macd_cross, macd_zero_favorable=macd_zero, macd_hist_favorable=hist_fav, bollinger_squeeze=squeeze, conviction_after_indecision=pa.indecision_to_conviction)
        ctx.score = score
        accepted = score.total >= cfg.strategy.minimum_confirmation_score
        # Liquidity Flow is an experimental research model. It may gate PAPER
        # only when explicitly enabled; LIVE is never gated by this model.
        lf = ctx.liquidity_flow
        if accepted and cfg.liquidity_flow.signal_gate_enabled and cfg.liquidity_flow.paper_only:
            if cfg.execution_mode.lower() == "paper":
                lf_ok = bool(lf and lf.liquidity_swept and lf.displacement_strength in {"MODERATE_DISPLACEMENT", "STRONG_DISPLACEMENT"} and lf.bos)
                accepted = accepted and lf_ok
                if not accepted:
                    return SignalDecision(desired, False, "Liquidity Flow experimental gate not confirmed", score, ctx)
        if accepted:
            sm.transition(StrategyState.RISK_CHECK, f"Score {score.total}/{score.maximum_possible}", now)
        return SignalDecision(desired, accepted, f"Score {score.total}/{score.maximum_possible}" if accepted else f"Score {score.total} < {cfg.strategy.minimum_confirmation_score}", score, ctx)
