from app.config.models import AppConfig
from app.config.settings import validate_config


def test_general_validation_does_not_require_live_mode():
    ok, errors = validate_config(AppConfig(execution_mode="paper"))
    assert ok, errors


def test_major_fx_symbol_universe_and_total_position_cap():
    from app.config.settings import load_settings, validate_config
    cfg = load_settings()
    ok, errors = validate_config(cfg)
    assert ok, errors
    assert {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"}.issubset(set(cfg.symbols))
    assert cfg.execution.max_positions_per_symbol == 1
    assert cfg.execution.max_total_open_positions >= 1
