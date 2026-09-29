from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from app.config.models import AppConfig, config_from_dict


def load_settings(path: str | Path = "app/config/default_config.yaml", env_file: str | Path | None = ".env") -> AppConfig:
    if env_file:
        load_dotenv(env_file, override=False)
    cfg_path = Path(path)
    data: dict[str, Any] = {}
    if cfg_path.exists():
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    if os.getenv("TRADING_SYMBOLS"):
        data["symbols"] = [x.strip().upper() for x in os.environ["TRADING_SYMBOLS"].split(",") if x.strip()]
        if data["symbols"]:
            data["symbol"] = data["symbols"][0]
    elif os.getenv("TRADING_SYMBOL"):
        data["symbol"] = os.environ["TRADING_SYMBOL"]
        data["symbols"] = [os.environ["TRADING_SYMBOL"].upper()]
    if os.getenv("TRADING_MODE"):
        data["execution_mode"] = os.environ["TRADING_MODE"]
    return config_from_dict(data)


def validate_config(config: AppConfig) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if config.risk.percent <= 0:
        errors.append("risk.percent must be > 0")
    if config.risk.max_risk_percent < config.risk.percent:
        errors.append("risk.max_risk_percent must be >= risk.percent")
    if config.risk.reward_risk < 1:
        errors.append("risk.reward_risk must be >= 1")
    if config.strategy.minimum_confirmation_score < 1:
        errors.append("minimum_confirmation_score must be >= 1")
    if config.four_hour_range.risk_reward != 2.0:
        errors.append("four_hour_range.risk_reward is fixed at 2.0 by the supplied strategy specification")
    if config.four_hour_range.entry_timeframe != "M5" or config.four_hour_range.range_timeframe != "H4":
        errors.append("four_hour_range requires H4 range and M5 entry timeframes")
    if config.backtest.profile not in {"broker_realistic", "research_unconstrained"}:
        errors.append("backtest.profile is invalid")
    if config.backtest.volume_min <= 0 or config.backtest.volume_step <= 0:
        errors.append("backtest volume_min and volume_step must be > 0")
    if config.risk.circuit_breaker_pause_after_losses <= config.risk.circuit_breaker_reduce_after_losses:
        errors.append("circuit breaker pause threshold must exceed reduction threshold")
    if config.execution.max_positions_per_symbol < 1:
        errors.append("execution.max_positions_per_symbol must be >= 1")
    if config.execution.max_total_open_positions < 1:
        errors.append("execution.max_total_open_positions must be >= 1")
    if not config.symbols:
        errors.append("symbols must contain at least one symbol")
    if any(not str(s).strip() for s in config.symbols):
        errors.append("symbols cannot contain empty names")
    if config.execution.max_trades_per_day < 1:
        errors.append("execution.max_trades_per_day must be >= 1")
    if config.execution.min_minutes_between_trades < 0:
        errors.append("execution.min_minutes_between_trades must be >= 0")
    if config.adaptive_learning.min_samples < 1:
        errors.append("adaptive_learning.min_samples must be >= 1")
    if not 0 < config.adaptive_learning.min_lower_confidence < 1:
        errors.append("adaptive_learning.min_lower_confidence must be in (0,1)")
    if not 0 < config.adaptive_learning.min_risk_multiplier <= config.adaptive_learning.max_risk_multiplier <= 1:
        errors.append("adaptive_learning risk multipliers must satisfy 0 < min <= max <= 1")
    if config.execution_mode.lower() == "live" and config.execution.live_strategy == "four_hour_range" and config.entry_timeframe != "M5":
        errors.append("four_hour_range live strategy requires entry_timeframe=M5")
    return (not errors, errors)


def validate_live_config(config: AppConfig) -> tuple[bool, list[str]]:
    errors: list[str] = []
    required = ["MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER"]
    for key in required:
        if not os.getenv(key):
            errors.append(f"Missing environment variable: {key}")
    if config.execution_mode.lower() != "live":
        errors.append("execution_mode must be 'live'")
    if config.risk.percent <= 0 or config.risk.percent > 10:
        errors.append("risk.percent must be in (0, 10]")
    if config.execution.require_demo_account and config.execution.allowed_demo_server:
        expected = os.getenv("MT5_EXPECTED_SERVER", config.execution.allowed_demo_server)
        if expected != config.execution.allowed_demo_server:
            errors.append("MT5_EXPECTED_SERVER does not match configured allowed_demo_server")
    return (not errors, errors)
