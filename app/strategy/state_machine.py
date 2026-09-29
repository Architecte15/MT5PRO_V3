from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.utils.enums import StrategyState, Trend


class InvalidStateTransition(RuntimeError):
    pass


_ALLOWED = {
    StrategyState.IDLE: {StrategyState.TREND_DETECTED},
    StrategyState.TREND_DETECTED: {StrategyState.BREAKOUT_DETECTED, StrategyState.IDLE},
    StrategyState.BREAKOUT_DETECTED: {StrategyState.WAITING_RETEST, StrategyState.IDLE},
    StrategyState.WAITING_RETEST: {StrategyState.RETEST_CONFIRMED, StrategyState.IDLE},
    StrategyState.RETEST_CONFIRMED: {StrategyState.WAITING_CONFIRMATION, StrategyState.IDLE},
    StrategyState.WAITING_CONFIRMATION: {StrategyState.INDICATOR_VALIDATION, StrategyState.IDLE},
    StrategyState.INDICATOR_VALIDATION: {StrategyState.RISK_CHECK, StrategyState.IDLE},
    StrategyState.RISK_CHECK: {StrategyState.ENTRY, StrategyState.IDLE},
    StrategyState.ENTRY: {StrategyState.POSITION_OPEN, StrategyState.IDLE},
    StrategyState.POSITION_OPEN: {StrategyState.POSITION_OPEN, StrategyState.IDLE},
}


@dataclass
class StrategyContext:
    symbol: str
    timeframe: str
    state: StrategyState = StrategyState.IDLE
    trend: Trend = Trend.NEUTRAL
    structure: object | None = None
    trendline: object | None = None
    breakout: object | None = None
    retest: object | None = None
    price_action: object | None = None
    indicators: object | None = None
    divergence: object | None = None
    score: object | None = None
    risk_assessment: object | None = None
    liquidity_flow: object | None = None
    adaptive_features: dict | None = None
    timestamps: dict[str, datetime] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


class StrategyStateMachine:
    def __init__(self, context: StrategyContext):
        self.context = context
        self.history: list[tuple[StrategyState, StrategyState, str, datetime]] = []

    def transition(self, new_state: StrategyState, reason: str, now: datetime) -> None:
        old = self.context.state
        if new_state not in _ALLOWED.get(old, set()):
            raise InvalidStateTransition(f"Invalid transition {old} -> {new_state}")
        self.context.state = new_state
        self.context.reasons.append(reason)
        self.context.timestamps[new_state.value] = now
        self.history.append((old, new_state, reason, now))
