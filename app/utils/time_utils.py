from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo


def in_session(ts: datetime, start: time, end: time, timezone: str = "UTC") -> bool:
    local = ts.astimezone(ZoneInfo(timezone))
    t = local.time().replace(tzinfo=None)
    s, e = start.replace(tzinfo=None), end.replace(tzinfo=None)
    if s == e:
        return True
    if s < e:
        return s <= t <= e
    return t >= s or t <= e
