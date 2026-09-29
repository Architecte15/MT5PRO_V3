from __future__ import annotations

from dataclasses import dataclass

from app.config.models import PositionManagementConfig
from app.utils.enums import Direction


@dataclass(frozen=True)
class ManagedStop:
    position_id: str
    new_sl: float | None = None
    close_percent: float = 0.0
    reason: str = ""


class StopManager:
    def __init__(self, config: PositionManagementConfig):
        self.config = config
        self.partial_done: set[str] = set()

    def update(self, position_id: str, direction: Direction, entry: float, current: float, current_sl: float, initial_risk: float, point_size: float) -> ManagedStop:
        profit_points = (current - entry) / point_size if direction is Direction.BUY else (entry - current) / point_size
        new_sl = None
        reason = ""
        if self.config.enable_break_even and profit_points >= self.config.break_even_trigger_points:
            candidate = entry + self.config.break_even_offset_points * point_size if direction is Direction.BUY else entry - self.config.break_even_offset_points * point_size
            if (direction is Direction.BUY and candidate > current_sl) or (direction is Direction.SELL and candidate < current_sl):
                new_sl, reason = candidate, "break_even"
        if self.config.enable_trailing_stop and profit_points >= self.config.trailing_stop_points:
            candidate = current - self.config.trailing_stop_points * point_size if direction is Direction.BUY else current + self.config.trailing_stop_points * point_size
            if (new_sl is None and ((direction is Direction.BUY and candidate > current_sl) or (direction is Direction.SELL and candidate < current_sl))) or (new_sl is not None and ((direction is Direction.BUY and candidate > new_sl) or (direction is Direction.SELL and candidate < new_sl))):
                new_sl, reason = candidate, "trailing"
        close_percent = 0.0
        if self.config.enable_partial_close and position_id not in self.partial_done and initial_risk > 0:
            rr = ((current - entry) / initial_risk) if direction is Direction.BUY else ((entry - current) / initial_risk)
            if rr >= self.config.partial_close_trigger_rr:
                close_percent = self.config.partial_close_percent
                self.partial_done.add(position_id)
                reason = "partial_close"
        return ManagedStop(position_id, new_sl, close_percent, reason)
