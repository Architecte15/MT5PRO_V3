from app.risk.circuit_breaker import RiskCircuitBreaker


def test_circuit_breaker_reduces_then_pauses():
    cb = RiskCircuitBreaker(reduce_after_losses=2, min_risk_multiplier=0.25, pause_after_losses=4, cooldown_bars=2)
    assert cb.multiplier() == 1.0
    cb.on_trade(-1); cb.on_trade(-1)
    assert cb.multiplier() < 1.0
    cb.on_trade(-1); cb.on_trade(-1)
    assert cb.multiplier() == 0.0
    assert not cb.can_trade()
