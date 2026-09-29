from app.config.models import AppConfig
from app.backtest.engine import BacktestEngine


def test_backtest_profile_is_explicit():
    cfg = AppConfig()
    assert cfg.backtest.profile in {"broker_realistic", "research_unconstrained"}


def test_research_and_realistic_starting_equity_differ_by_default():
    cfg = AppConfig()
    assert cfg.backtest.starting_equity == 17.65
    assert BacktestEngine(cfg).config.backtest.max_open_positions == 1
