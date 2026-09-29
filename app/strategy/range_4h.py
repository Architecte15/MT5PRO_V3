from __future__ import annotations

from dataclasses import dataclass
from datetime import time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from app.strategy.market_structure import detect_swings
from app.utils.enums import Direction


@dataclass(frozen=True)
class FourHourRange:
    session_date: str
    timezone: str
    open_time: pd.Timestamp
    close_time: pd.Timestamp
    high: float
    low: float


@dataclass(frozen=True)
class RangeScalpSignal:
    session_date: str
    direction: Direction
    range_high: float
    range_low: float
    breakout_time: pd.Timestamp
    reentry_time: pd.Timestamp
    entry_time: pd.Timestamp
    entry_price: float
    breakout_extreme: float
    stop_loss: float
    take_profit: float
    risk_distance: float
    used_fallback_sl: bool
    reason: str


def _as_utc_index(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().sort_index()
    idx = pd.DatetimeIndex(out.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")
    out.index = idx
    return out


def _ny_index(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    idx = index
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    return idx.tz_convert("America/New_York")


def build_first_h4_ranges(h4_df: pd.DataFrame, timezone: str = "America/New_York") -> dict[str, FourHourRange]:
    """Build one range from the first H4 candle of each local calendar day.

    The range is usable only after that H4 candle has fully closed. No future
    H4 bar is consulted for the range itself.
    """
    if h4_df.empty:
        return {}
    df = _as_utc_index(h4_df)
    local = df.index.tz_convert(timezone)
    days = local.date
    result: dict[str, FourHourRange] = {}
    for day in sorted(set(days)):
        positions = [i for i, d in enumerate(days) if d == day]
        if not positions:
            continue
        i = positions[0]
        row = df.iloc[i]
        open_time = pd.Timestamp(df.index[i])
        close_time = open_time + pd.Timedelta(hours=4)
        key = str(day)
        result[key] = FourHourRange(
            session_date=key,
            timezone=timezone,
            open_time=open_time,
            close_time=close_time,
            high=float(row["high"]),
            low=float(row["low"]),
        )
    return result


def _nearest_fallback_sl(
    m5_before_entry: pd.DataFrame,
    direction: Direction,
    entry: float,
    range_high: float,
    range_low: float,
    swing_strength: int,
) -> float | None:
    """Choose the nearest causal structural level on the protective side."""
    candidates: list[float] = []
    if direction is Direction.BUY and range_low < entry:
        candidates.append(range_low)
    if direction is Direction.SELL and range_high > entry:
        candidates.append(range_high)
    try:
        swings = detect_swings(m5_before_entry, swing_strength)
    except Exception:
        swings = []
    if direction is Direction.BUY:
        candidates.extend(s.price for s in swings if s.type.value == "LOW" and s.price < entry)
        return max(candidates) if candidates else None
    candidates.extend(s.price for s in swings if s.type.value == "HIGH" and s.price > entry)
    return min(candidates) if candidates else None


def detect_range_scalp_signals(
    m5_df: pd.DataFrame,
    h4_df: pd.DataFrame,
    *,
    timezone: str = "America/New_York",
    max_sl_points: float = 500.0,
    point_size: float = 0.00001,
    fallback_sl_enabled: bool = True,
    swing_strength: int = 2,
    allow_multiple_per_day: bool = True,
) -> list[RangeScalpSignal]:
    """Detect the 4H-first-candle breakout/re-entry setup on closed M5 candles.

    Sequence: completed first H4 range -> M5 close outside -> later M5 close
    back inside -> entry on the next M5 open. Breakout extremes are computed
    only from candles available before that entry.
    """
    if m5_df.empty or h4_df.empty:
        return []
    m5 = _as_utc_index(m5_df)
    ranges = build_first_h4_ranges(h4_df, timezone)
    local = m5.index.tz_convert(timezone)
    signals: list[RangeScalpSignal] = []

    for day, rng in ranges.items():
        day_mask = local.date.astype(str) == day
        day_positions = [i for i, ok in enumerate(day_mask) if ok]
        if not day_positions:
            continue
        eligible = [i for i in day_positions if m5.index[i] >= rng.close_time]
        if len(eligible) < 2:
            continue
        state: str | None = None
        breakout_idx: int | None = None
        last_signal_idx = -1
        for pos in eligible:
            if pos >= len(m5) - 1:
                break
            close = float(m5.iloc[pos]["close"])
            high = float(m5.iloc[pos]["high"])
            low = float(m5.iloc[pos]["low"])
            if state is None:
                if close > rng.high:
                    state = "ABOVE"
                    breakout_idx = pos
                elif close < rng.low:
                    state = "BELOW"
                    breakout_idx = pos
                continue

            if state == "ABOVE" and close <= rng.high and close >= rng.low:
                signal = _make_signal(m5, rng, Direction.SELL, breakout_idx, pos, timezone, max_sl_points, point_size, fallback_sl_enabled, swing_strength)
                if signal:
                    signals.append(signal)
                    last_signal_idx = pos
                state = None if allow_multiple_per_day else "DONE"
                breakout_idx = None
            elif state == "BELOW" and close >= rng.low and close <= rng.high:
                signal = _make_signal(m5, rng, Direction.BUY, breakout_idx, pos, timezone, max_sl_points, point_size, fallback_sl_enabled, swing_strength)
                if signal:
                    signals.append(signal)
                    last_signal_idx = pos
                state = None if allow_multiple_per_day else "DONE"
                breakout_idx = None
            elif state == "DONE":
                break

    return signals


def _make_signal(
    m5: pd.DataFrame,
    rng: FourHourRange,
    direction: Direction,
    breakout_idx: int | None,
    reentry_idx: int,
    timezone: str,
    max_sl_points: float,
    point_size: float,
    fallback_sl_enabled: bool,
    swing_strength: int,
) -> RangeScalpSignal | None:
    if breakout_idx is None or reentry_idx <= breakout_idx or reentry_idx + 1 >= len(m5):
        return None
    entry_idx = reentry_idx + 1
    entry_time = pd.Timestamp(m5.index[entry_idx])
    local_entry = entry_time.tz_convert(timezone)
    if str(local_entry.date()) != rng.session_date:
        return None
    entry = float(m5.iloc[entry_idx]["open"])
    movement = m5.iloc[breakout_idx : reentry_idx + 1]
    breakout_extreme = float(movement["high"].max() if direction is Direction.SELL else movement["low"].min())
    sl = breakout_extreme
    used_fallback = False
    distance = abs(entry - sl)
    if (direction is Direction.BUY and sl >= entry) or (direction is Direction.SELL and sl <= entry):
        return None
    if distance / point_size > max_sl_points and fallback_sl_enabled:
        fallback = _nearest_fallback_sl(m5.iloc[:entry_idx], direction, entry, rng.high, rng.low, swing_strength)
        if fallback is not None:
            sl = float(fallback)
            used_fallback = True
            distance = abs(entry - sl)
    if distance <= 0 or distance / point_size > max_sl_points:
        return None
    tp = entry + 2.0 * distance if direction is Direction.BUY else entry - 2.0 * distance
    return RangeScalpSignal(
        session_date=rng.session_date,
        direction=direction,
        range_high=rng.high,
        range_low=rng.low,
        breakout_time=pd.Timestamp(m5.index[breakout_idx]),
        reentry_time=pd.Timestamp(m5.index[reentry_idx]),
        entry_time=entry_time,
        entry_price=entry,
        breakout_extreme=breakout_extreme,
        stop_loss=sl,
        take_profit=tp,
        risk_distance=distance,
        used_fallback_sl=used_fallback,
        reason="M5 close outside first H4 range followed by closed-candle re-entry",
    )
