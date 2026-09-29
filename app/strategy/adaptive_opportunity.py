from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd

from app.config.models import AppConfig
from app.strategy.indicators import add_indicators
from app.strategy.market_structure import detect_swings, classify_structure
from app.strategy.state_machine import StrategyContext
from app.utils.enums import Direction, Trend


@dataclass(frozen=True)
class AdaptiveOpportunity:
    direction: Direction
    context: StrategyContext
    features: dict
    reason: str
    quality: float


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr = pd.concat([
        df.high - df.low,
        (df.high - df.close.shift()).abs(),
        (df.low - df.close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def scan(entry_df: pd.DataFrame, htf_df: pd.DataFrame, cfg: AppConfig) -> AdaptiveOpportunity | None:
    if len(entry_df) < 80 or len(htf_df) < 60:
        return None
    e = add_indicators(entry_df, cfg.indicators)
    h = add_indicators(htf_df, cfg.indicators)
    last = e.iloc[-1]
    prev = e.iloc[-2]
    atr = float(_atr(e).iloc[-1])
    if not np.isfinite(atr) or atr <= 0:
        return None
    ema13 = e["close"].ewm(span=13, adjust=False).mean()
    ema50 = e["close"].ewm(span=50, adjust=False).mean()
    htf_up = float(h.close.iloc[-1]) > float(h.ema.iloc[-1]) and float(h.ema.iloc[-1]) > float(h.ema.iloc[-2])
    htf_down = float(h.close.iloc[-1]) < float(h.ema.iloc[-1]) and float(h.ema.iloc[-1]) < float(h.ema.iloc[-2])
    slope13 = float(ema13.iloc[-1] - ema13.iloc[-4])
    slope50 = float(ema50.iloc[-1] - ema50.iloc[-4])
    body_atr = abs(float(last.close-last.open))/atr
    bull = htf_up and float(last.close) > float(ema50.iloc[-1]) and slope13 > 0 and slope50 >= 0
    bear = htf_down and float(last.close) < float(ema50.iloc[-1]) and slope13 < 0 and slope50 <= 0
    pullback_bull = bool(e.iloc[-3:]["low"].min() <= ema13.iloc[-3:].max())
    pullback_bear = bool(e.iloc[-3:]["high"].max() >= ema13.iloc[-3:].min())
    bull_confirm = float(last.close) > float(prev.high) and float(last.close) > float(last.open) and body_atr >= 0.35
    bear_confirm = float(last.close) < float(prev.low) and float(last.close) < float(last.open) and body_atr >= 0.35
    direction = Direction.BUY if bull and pullback_bull and bull_confirm else Direction.SELL if bear and pullback_bear and bear_confirm else Direction.FLAT
    if direction is Direction.FLAT:
        return None
    swings = detect_swings(e, cfg.strategy.swing_strength)
    structure = classify_structure(swings)
    trend = Trend.BULLISH if direction is Direction.BUY else Trend.BEARISH
    ctx = StrategyContext(cfg.symbol, cfg.entry_timeframe, trend=trend, structure=structure)
    rsi = float(last.rsi) if np.isfinite(float(last.rsi)) else 50.0
    ema_side = "ABOVE" if float(last.close) >= float(ema13.iloc[-1]) else "BELOW"
    rel_vol = atr / max(abs(float(last.close)), 1e-12)
    features = {
        "direction": direction.value,
        "regime": "UPTREND" if direction is Direction.BUY else "DOWNTREND",
        "session": str(last.name.hour),
        "trend_alignment": "HTF_ALIGNED",
        "pullback": "EMA13_RETEST",
        "momentum": "STRONG" if body_atr >= 0.8 else "MODERATE",
        "volatility": "HIGH" if rel_vol >= 0.0015 else "NORMAL",
        "ema13_side": ema_side,
        "structure_bias": "BULLISH" if structure.bullish else "BEARISH" if structure.bearish else "MIXED",
        "body_atr": round(body_atr, 4),
        "rsi": round(rsi, 2),
    }
    quality = 0.0
    quality += 1.0 if (htf_up if direction is Direction.BUY else htf_down) else 0.0
    quality += 1.0 if (float(last.close) > float(ema13.iloc[-1]) if direction is Direction.BUY else float(last.close) < float(ema13.iloc[-1])) else 0.0
    quality += 1.0 if body_atr >= 0.35 else 0.0
    quality += 1.0 if body_atr >= 0.8 else 0.0
    quality += 1.0 if (rsi >= 50 if direction is Direction.BUY else rsi <= 50) else 0.0
    return AdaptiveOpportunity(direction, ctx, features, f"Adaptive trend/pullback opportunity quality={quality:.1f}/5", quality)
