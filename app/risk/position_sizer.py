from __future__ import annotations

from dataclasses import dataclass

from app.utils.math_utils import round_down_step


@dataclass(frozen=True)
class SymbolSpec:
    point_size: float
    tick_size: float
    tick_value: float
    contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    stops_level_points: float = 0.0
    freeze_level_points: float = 0.0


class PositionSizingError(ValueError):
    pass


def calculate_volume(balance: float, risk_percent: float, entry: float, sl: float, spec: SymbolSpec, use_equity_value: float | None = None) -> float:
    capital = use_equity_value if use_equity_value is not None else balance
    if capital <= 0 or risk_percent <= 0:
        raise PositionSizingError("Capital and risk_percent must be positive")
    distance = abs(entry - sl)
    if distance <= 0 or spec.tick_size <= 0 or spec.tick_value <= 0:
        raise PositionSizingError("Invalid price distance or symbol tick configuration")
    risk_money = capital * risk_percent / 100.0
    money_per_lot = (distance / spec.tick_size) * spec.tick_value
    raw = risk_money / money_per_lot
    volume = round_down_step(raw, spec.volume_step)
    if volume < spec.volume_min:
        return 0.0
    return min(volume, spec.volume_max)


def risk_money_for_volume(entry: float, sl: float, volume: float, spec: SymbolSpec) -> float:
    distance = abs(entry - sl)
    return (distance / spec.tick_size) * spec.tick_value * volume


def approximate_margin_per_lot(entry: float, spec: SymbolSpec, leverage: float) -> float:
    if leverage <= 0:
        raise PositionSizingError("Leverage must be positive")
    return abs(entry) * spec.contract_size / leverage
