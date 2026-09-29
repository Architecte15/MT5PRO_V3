from datetime import datetime, timezone
import pytest

from app.strategy.state_machine import StrategyContext, StrategyStateMachine, InvalidStateTransition
from app.utils.enums import StrategyState


def test_valid_transitions():
    ctx = StrategyContext("EURUSD", "M15")
    sm = StrategyStateMachine(ctx)
    now = datetime.now(timezone.utc)
    sm.transition(StrategyState.TREND_DETECTED, "trend", now)
    sm.transition(StrategyState.BREAKOUT_DETECTED, "breakout", now)
    assert ctx.state is StrategyState.BREAKOUT_DETECTED


def test_invalid_transition():
    ctx = StrategyContext("EURUSD", "M15")
    sm = StrategyStateMachine(ctx)
    with pytest.raises(InvalidStateTransition):
        sm.transition(StrategyState.ENTRY, "skip", datetime.now(timezone.utc))
