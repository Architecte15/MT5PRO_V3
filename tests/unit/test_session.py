from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
from app.utils.time_utils import in_session


def test_normal_session():
    ts = datetime(2026, 1, 1, 10, 0, tzinfo=ZoneInfo("UTC"))
    assert in_session(ts, time(7), time(21), "UTC")


def test_cross_midnight_session():
    ts = datetime(2026, 1, 1, 23, 0, tzinfo=timezone.utc)
    assert in_session(ts, time(22), time(2), "UTC")
