from __future__ import annotations

from datetime import timedelta

_TIMEFRAME_MINUTES = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 60, "H4": 240, "D1": 1440, "W1": 10080,
}


def timeframe_minutes(timeframe: str) -> int:
    key = timeframe.upper()
    if key not in _TIMEFRAME_MINUTES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return _TIMEFRAME_MINUTES[key]


def timeframe_delta(timeframe: str) -> timedelta:
    return timedelta(minutes=timeframe_minutes(timeframe))
