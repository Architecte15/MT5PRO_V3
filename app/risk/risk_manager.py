from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.config.models import AppConfig
from app.data.tick import Tick
from app.risk.position_sizer import SymbolSpec, calculate_volume, risk_money_for_volume, approximate_margin_per_lot
from app.utils.enums import Direction
from app.utils.time_utils import in_session


@dataclass(frozen=True)
class RiskAssessment:
    accepted: bool
    entry: float
    sl: float
    tp: float
    volume: float
    rr: float
    reasons: tuple[str, ...]
    risk_money: float = 0.0
    margin_required: float = 0.0
    effective_risk_percent: float = 0.0


class RiskManager:
    def __init__(self, config: AppConfig):
        self.config = config

    def build_stops(self, direction: Direction, entry: float, swing_price: float) -> tuple[float, float]:
        buffer = self.config.risk.sl_buffer_points * self.config.point_size
        sl = swing_price - buffer if direction is Direction.BUY else swing_price + buffer
        dist = abs(entry - sl)
        rr = self.config.risk.reward_risk
        tp = entry + dist * rr if direction is Direction.BUY else entry - dist * rr
        return sl, tp

    def assess(self, direction: Direction, entry: float, sl: float, spec: SymbolSpec,
               account_balance: float, account_equity: float, tick: Tick, now: datetime,
               margin_per_lot: float | None = None, free_margin: float | None = None,
               risk_multiplier: float = 1.0) -> RiskAssessment:
        reasons: list[str] = []
        if direction is Direction.BUY and sl >= entry:
            reasons.append("Invalid SL side for BUY: SL must be below entry")
        elif direction is Direction.SELL and sl <= entry:
            reasons.append("Invalid SL side for SELL: SL must be above entry")

        dist_points = abs(entry - sl) / self.config.point_size
        if dist_points <= 0:
            reasons.append("Invalid SL distance")
        if dist_points > self.config.risk.max_sl_points:
            reasons.append("SL distance exceeds max_sl_points")
        if dist_points < spec.stops_level_points:
            reasons.append("SL distance below broker stops level")
        spread_points = tick.spread / self.config.point_size
        if spread_points > self.config.risk.max_spread_points:
            reasons.append("Spread too high")
        if self.config.session.enabled and not in_session(now, self.config.session.start, self.config.session.end, self.config.session.timezone):
            reasons.append("Outside trading session")
        if risk_multiplier <= 0:
            reasons.append("Risk circuit breaker is paused")

        volume = 0.0
        risk_money = 0.0
        margin_required = 0.0
        effective_percent = 0.0
        if not reasons:
            effective_percent = min(self.config.risk.percent * risk_multiplier, self.config.risk.max_risk_percent)
            capital = account_equity if self.config.risk.use_equity else account_balance
            volume = calculate_volume(account_balance, effective_percent, entry, sl, spec, capital if self.config.risk.use_equity else None)
            if volume < spec.volume_min and self.config.risk.allow_min_volume_if_affordable:
                min_risk = risk_money_for_volume(entry, sl, spec.volume_min, spec)
                min_risk_pct = 100.0 * min_risk / max(capital, 1e-12)
                if min_risk_pct <= self.config.risk.max_min_volume_risk_percent:
                    volume = spec.volume_min
            if volume < spec.volume_min:
                reasons.append("Calculated volume below broker minimum")
            if volume > 0:
                risk_money = risk_money_for_volume(entry, sl, volume, spec)
                if margin_per_lot is not None:
                    margin_required = margin_per_lot * volume
                else:
                    margin_required = approximate_margin_per_lot(entry, spec, self.config.backtest.leverage) * volume
                if free_margin is not None and margin_required > free_margin:
                    reasons.append(f"Insufficient margin: required={margin_required:.4f}, free={free_margin:.4f}")
                effective_percent = 100.0 * risk_money / max(capital, 1e-12)
                if effective_percent > self.config.risk.max_min_volume_risk_percent and volume == spec.volume_min:
                    reasons.append("Minimum volume would exceed configured risk ceiling")

        distance = abs(entry - sl)
        tp = entry + distance * self.config.risk.reward_risk if direction is Direction.BUY else entry - distance * self.config.risk.reward_risk
        rr = abs(tp - entry) / distance if distance > 0 else 0.0
        return RiskAssessment(not reasons, entry, sl, tp, volume, rr, tuple(reasons), risk_money, margin_required, effective_percent)
