from datetime import datetime, timezone

from app.adaptive.learner import AdaptiveLearner, AdaptiveObservation


def test_adaptive_memory_learns_only_after_close(tmp_path):
    learner = AdaptiveLearner(str(tmp_path / "adaptive.sqlite3"), min_samples=2, min_lower_confidence=0.4)
    features = {
        "direction": "BUY", "regime": "UPTREND", "session": "14",
        "trend_alignment": "HTF_ALIGNED", "pullback": "EMA13_RETEST",
        "momentum": "STRONG", "volatility": "NORMAL", "ema13_side": "ABOVE",
        "structure_bias": "BULLISH",
    }
    key = learner.context_key(features)
    learner.observe_entry(AdaptiveObservation("p1", "EURUSD", "BUY", "ADAPTIVE", key, "t", 1.1, 1.099, 1.102, features))
    assert learner.stats(key)["samples"] == 0
    assert learner.opportunity_allowed(key)[0] is True
    learner.observe_outcome("p1", 0.10, datetime.now(timezone.utc), "TP")
    learner.observe_entry(AdaptiveObservation("p2", "EURUSD", "BUY", "ADAPTIVE", key, "t2", 1.1, 1.099, 1.102, features))
    learner.observe_outcome("p2", 0.10, datetime.now(timezone.utc), "TP")
    stats = learner.stats(key)
    assert stats["samples"] == 2
    assert stats["wins"] == 2
    assert stats["win_rate"] > 0.8


def test_adaptive_loss_reduces_risk_after_min_samples(tmp_path):
    learner = AdaptiveLearner(str(tmp_path / "adaptive.sqlite3"), min_samples=2, min_lower_confidence=0.8, min_risk_multiplier=0.25)
    features = {"direction":"SELL","regime":"DOWNTREND","session":"9","trend_alignment":"BEARISH","pullback":"EMA13_RETEST","momentum":"MODERATE","volatility":"NORMAL","ema13_side":"BELOW","structure_bias":"BEARISH"}
    key = learner.context_key(features)
    for i, pnl in enumerate([-0.1, -0.1]):
        pid = f"p{i}"
        learner.observe_entry(AdaptiveObservation(pid,"EURUSD","SELL","ADAPTIVE",key,"t",1.1,1.101,1.098,features))
        learner.observe_outcome(pid,pnl)
    assert learner.risk_multiplier(key) <= 1.0
    assert learner.risk_multiplier(key) >= 0.25
