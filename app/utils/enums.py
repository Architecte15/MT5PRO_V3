from __future__ import annotations

from enum import Enum


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    FLAT = "FLAT"

    @property
    def sign(self) -> int:
        return 1 if self is Direction.BUY else -1 if self is Direction.SELL else 0

    @property
    def opposite(self) -> "Direction":
        if self is Direction.BUY:
            return Direction.SELL
        if self is Direction.SELL:
            return Direction.BUY
        return Direction.FLAT


class Trend(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class SwingType(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


class StructureType(str, Enum):
    HH = "HH"
    HL = "HL"
    LH = "LH"
    LL = "LL"
    MIXED = "MIXED"
    NONE = "NONE"


class StrategyState(str, Enum):
    IDLE = "STATE_IDLE"
    TREND_DETECTED = "STATE_TREND_DETECTED"
    BREAKOUT_DETECTED = "STATE_BREAKOUT_DETECTED"
    WAITING_RETEST = "STATE_WAITING_RETEST"
    RETEST_CONFIRMED = "STATE_RETEST_CONFIRMED"
    WAITING_CONFIRMATION = "STATE_WAITING_CONFIRMATION"
    INDICATOR_VALIDATION = "STATE_INDICATOR_VALIDATION"
    RISK_CHECK = "STATE_RISK_CHECK"
    ENTRY = "STATE_ENTRY"
    POSITION_OPEN = "STATE_POSITION_OPEN"


class OrderStatus(str, Enum):
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    PENDING = "PENDING"


class TimeInForce(str, Enum):
    GTC = "GTC"
    IOC = "IOC"


class TPMode(str, Enum):
    RR = "TP_BY_RR"
    STRUCTURE = "TP_STRUCTURE"
