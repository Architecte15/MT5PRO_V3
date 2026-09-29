from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from typing import Any


@dataclass(frozen=True)
class RiskConfig:
    percent: float = 1.0
    max_open_positions: int = 1
    max_sl_points: float = 500.0
    max_spread_points: float = 30.0
    daily_loss_limit_percent: float = 3.0
    reward_risk: float = 2.0
    sl_buffer_points: float = 5.0
    use_equity: bool = True
    compound: bool = True
    max_risk_percent: float = 3.0
    allow_min_volume_if_affordable: bool = True
    max_min_volume_risk_percent: float = 3.0
    circuit_breaker_reduce_after_losses: int = 4
    circuit_breaker_pause_after_losses: int = 8
    circuit_breaker_min_multiplier: float = 0.25
    circuit_breaker_cooldown_bars: int = 3


@dataclass(frozen=True)
class StrategyConfig:
    minimum_confirmation_score: int = 7
    breakout_buffer_points: float = 10.0
    retest_tolerance_points: float = 20.0
    max_retest_bars: int = 10
    max_confirmation_bars: int = 5
    swing_lookback: int = 3
    swing_strength: int = 2
    allow_counter_trend_trades: bool = False
    use_higher_timeframe_filter: bool = True
    close_on_opposite_signal: bool = False
    max_signal_age_bars: int = 50


@dataclass(frozen=True)
class BacktestConfig:
    profile: str = "broker_realistic"
    max_open_positions: int = 1
    starting_equity: float = 17.65
    leverage: float = 100.0
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    tick_size: float = 0.00001
    tick_value: float = 1.0
    contract_size: float = 100000.0
    commission_per_lot: float = 0.0
    slippage_points: float = 0.0
    margin_per_lot: float | None = None
    required_filling_mode: str = "FOK"


@dataclass(frozen=True)
class FourHourRangeConfig:
    enabled: bool = True
    timezone: str = "America/New_York"
    range_timeframe: str = "H4"
    entry_timeframe: str = "M5"
    max_sl_points: float = 500.0
    fallback_sl_enabled: bool = True
    swing_strength: int = 2
    allow_multiple_per_day: bool = True
    risk_reward: float = 2.0
    signal_gate_enabled: bool = False
    paper_only: bool = True


@dataclass(frozen=True)
class LiquidityFlowConfig:
    enabled: bool = True
    signal_gate_enabled: bool = False
    paper_only: bool = True
    feature_version: str = "LF-1.0"
    swing_strength: int = 2
    zone_tolerance_points: float = 15.0
    displacement_weak_body_atr: float = 0.5
    displacement_moderate_body_atr: float = 1.0
    displacement_strong_body_atr: float = 1.5
    outcome_horizon_bars: int = 12
    min_samples: int = 100
    drift_psi_threshold: float = 0.25
    use_ema13_feature: bool = True


@dataclass(frozen=True)
class AdaptiveLearningConfig:
    enabled: bool = True
    opportunity_scan_enabled: bool = True
    memory_db_path: str = "runtime/adaptive_memory.sqlite3"
    min_samples: int = 20
    min_lower_confidence: float = 0.48
    min_risk_multiplier: float = 0.35
    max_risk_multiplier: float = 1.0
    cold_start_allowed: bool = True
    learn_after_close_only: bool = True
    model_version: str = "ADAPTIVE-1.0"


@dataclass(frozen=True)
class IndicatorConfig:
    ema_period: int = 200
    bollinger_period: int = 20
    bollinger_deviation: float = 2.0
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    squeeze_lookback: int = 50
    squeeze_threshold: float = 0.08
    minimum_squeeze_candles: int = 5
    momentum_factor: float = 1.8
    wick_ratio: float = 2.0
    divergence_lookback: int = 30


@dataclass(frozen=True)
class SessionConfig:
    enabled: bool = True
    start: time = time(7, 0)
    end: time = time(21, 0)
    timezone: str = "UTC"


@dataclass(frozen=True)
class ExecutionConfig:
    max_positions_per_symbol: int = 1
    max_total_open_positions: int = 3
    allow_hedging: bool = False
    allow_opposite_entry: bool = False
    signal_cooldown_seconds: float = 30.0
    order_lock_timeout_seconds: float = 10.0
    guard_db_path: str = "runtime/execution_guard.sqlite3"
    live_strategy: str = "four_hour_range"
    require_demo_account: bool = True
    allowed_demo_server: str = "MetaQuotes-Demo"
    max_trades_per_day: int = 12
    min_minutes_between_trades: float = 5.0
    scan_all_configured_symbols: bool = True
    skip_unavailable_symbols: bool = True


@dataclass(frozen=True)
class PositionManagementConfig:
    enable_break_even: bool = True
    break_even_trigger_points: float = 100.0
    break_even_offset_points: float = 2.0
    enable_trailing_stop: bool = True
    trailing_stop_points: float = 120.0
    enable_partial_close: bool = False
    partial_close_percent: float = 50.0
    partial_close_trigger_rr: float = 1.0


@dataclass(frozen=True)
class AppConfig:
    symbol: str = "EURUSD"
    symbols: tuple[str, ...] = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD")
    higher_timeframe: str = "H4"
    entry_timeframe: str = "M15"
    strategy_id: str = "PY-PA-001"
    point_size: float = 0.00001
    account_currency: str = "USD"
    risk: RiskConfig = field(default_factory=RiskConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    indicators: IndicatorConfig = field(default_factory=IndicatorConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    position_management: PositionManagementConfig = field(default_factory=PositionManagementConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    liquidity_flow: LiquidityFlowConfig = field(default_factory=LiquidityFlowConfig)
    adaptive_learning: AdaptiveLearningConfig = field(default_factory=AdaptiveLearningConfig)
    four_hour_range: FourHourRangeConfig = field(default_factory=FourHourRangeConfig)
    execution_mode: str = "paper"


def _parse_hhmm(value: str | time) -> time:
    if isinstance(value, time):
        return value
    hour, minute = [int(x) for x in str(value).split(":", 1)]
    return time(hour, minute)


def _merge_dataclass(cls, raw: dict[str, Any]):
    return cls(**raw)


def config_from_dict(raw: dict[str, Any]) -> AppConfig:
    risk = _merge_dataclass(RiskConfig, raw.get("risk", {}))
    strategy = _merge_dataclass(StrategyConfig, raw.get("strategy", {}))
    indicators = _merge_dataclass(IndicatorConfig, raw.get("indicators", {}))
    session_raw = dict(raw.get("session", {}))
    session_raw["start"] = _parse_hhmm(session_raw.get("start", "07:00"))
    session_raw["end"] = _parse_hhmm(session_raw.get("end", "21:00"))
    session = _merge_dataclass(SessionConfig, session_raw)
    pm = _merge_dataclass(PositionManagementConfig, raw.get("position_management", {}))
    execution = _merge_dataclass(ExecutionConfig, raw.get("execution", {}))
    bt = _merge_dataclass(BacktestConfig, raw.get("backtest", {}))
    lf = _merge_dataclass(LiquidityFlowConfig, raw.get("liquidity_flow", {}))
    adaptive = _merge_dataclass(AdaptiveLearningConfig, raw.get("adaptive_learning", {}))
    fr = _merge_dataclass(FourHourRangeConfig, raw.get("four_hour_range", {}))
    top = {k: v for k, v in raw.items() if k not in {"risk", "strategy", "indicators", "session", "position_management", "execution", "backtest", "liquidity_flow", "adaptive_learning", "four_hour_range"}}
    if "symbols" in top:
        top["symbols"] = tuple(str(x).upper() for x in top["symbols"])
    elif "symbol" in top:
        top["symbols"] = (str(top["symbol"]).upper(),)
    return AppConfig(**top, risk=risk, strategy=strategy, indicators=indicators, session=session, position_management=pm, execution=execution, backtest=bt, liquidity_flow=lf, adaptive_learning=adaptive, four_hour_range=fr)
