from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskCircuitBreaker:
    reduce_after_losses: int = 4
    min_risk_multiplier: float = 0.25
    pause_after_losses: int = 8
    cooldown_bars: int = 3
    consecutive_losses: int = 0
    cooldown_remaining: int = 0

    def multiplier(self) -> float:
        if self.consecutive_losses >= self.pause_after_losses:
            return 0.0
        if self.consecutive_losses < self.reduce_after_losses:
            return 1.0
        steps = self.consecutive_losses - self.reduce_after_losses + 1
        return max(self.min_risk_multiplier, 0.5 ** steps)

    def can_trade(self) -> bool:
        return self.cooldown_remaining <= 0 and self.multiplier() > 0

    def on_trade(self, pnl: float) -> None:
        if pnl < 0:
            self.consecutive_losses += 1
            self.cooldown_remaining = self.cooldown_bars if self.consecutive_losses >= self.pause_after_losses else 0
        elif pnl > 0:
            self.consecutive_losses = 0
            self.cooldown_remaining = 0

    def on_new_bar(self) -> None:
        if self.cooldown_remaining > 0:
            self.cooldown_remaining -= 1
