from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np

from app.config.models import AppConfig
from app.strategy.liquidity_flow.model import LiquidityType, DisplacementStrength


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr = pd.concat([(df.high-df.low), (df.high-df.close.shift()).abs(), (df.low-df.close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def _confirmed_swings(df: pd.DataFrame, strength: int) -> tuple[np.ndarray, np.ndarray]:
    h = df.high.to_numpy(float); l = df.low.to_numpy(float); n=len(df)
    sh=np.zeros(n,dtype=bool); sl=np.zeros(n,dtype=bool)
    if n <= 2*strength: return sh, sl
    for i in range(strength, n-strength):
        sh[i] = h[i] > h[i-strength:i].max() and h[i] >= h[i+1:i+strength+1].max()
        sl[i] = l[i] < l[i-strength:i].min() and l[i] <= l[i+1:i+strength+1].min()
    return sh, sl


def build_observation_dataset(df: pd.DataFrame, config: AppConfig, horizon_bars: int = 12) -> pd.DataFrame:
    """Fast causal dataset builder. Features at t only use confirmed swings strictly before t."""
    df=df.sort_index().copy(); n=len(df)
    if n <= horizon_bars + 20: return pd.DataFrame()
    atr=_atr(df,14).to_numpy(float)
    ema13=df.close.ewm(span=13,adjust=False).mean().to_numpy(float)
    ema50=df.close.ewm(span=50,adjust=False).mean().to_numpy(float)
    sh,sl=_confirmed_swings(df, config.liquidity_flow.swing_strength)
    high=df.high.to_numpy(float); low=df.low.to_numpy(float); close=df.close.to_numpy(float); op=df.open.to_numpy(float)
    rows=[]; warmup=max(80, config.indicators.ema_period//2)
    for i in range(warmup, n-horizon_bars):
        prior_hi=np.flatnonzero(sh[:i-1]); prior_lo=np.flatnonzero(sl[:i-1])
        buy_levels=high[prior_hi] if len(prior_hi) else np.array([])
        sell_levels=low[prior_lo] if len(prior_lo) else np.array([])
        price=close[i]
        buy_level=float(buy_levels[buy_levels>=price].min()) if np.any(buy_levels>=price) else np.nan
        sell_level=float(sell_levels[sell_levels<=price].max()) if np.any(sell_levels<=price) else np.nan
        sweep_dir="FLAT"; swept=False; overshoot=0.0
        if len(sell_levels):
            level=float(sell_levels[-1])
            if low[i] < level and close[i] > level:
                sweep_dir="BUY"; swept=True; overshoot=level-low[i]
        if len(buy_levels):
            level=float(buy_levels[-1])
            if high[i] > level and close[i] < level and not swept:
                sweep_dir="SELL"; swept=True; overshoot=high[i]-level
        body=abs(close[i]-op[i]); rng=high[i]-low[i]
        body_atr=body/atr[i] if np.isfinite(atr[i]) and atr[i]>0 else np.nan
        directional = 0
        if swept:
            sign=1 if sweep_dir=="BUY" else -1
            for j in range(i,min(i+3,n)):
                if (1 if close[j]>op[j] else -1 if close[j]<op[j] else 0)==sign: directional+=1
                else: break
        if np.isfinite(body_atr) and body_atr>=1.5 and directional>=2: disp=DisplacementStrength.STRONG_DISPLACEMENT.value
        elif np.isfinite(body_atr) and body_atr>=1.0 and directional>=1: disp=DisplacementStrength.MODERATE_DISPLACEMENT.value
        elif np.isfinite(body_atr) and body_atr>=0.5: disp=DisplacementStrength.WEAK_DISPLACEMENT.value
        else: disp=DisplacementStrength.NO_DISPLACEMENT.value
        recent_hi=high[prior_hi[-2:]] if len(prior_hi) else np.array([]); recent_lo=low[prior_lo[-2:]] if len(prior_lo) else np.array([])
        bos=(sweep_dir=="BUY" and len(recent_hi) and price>recent_hi.max()) or (sweep_dir=="SELL" and len(recent_lo) and price<recent_lo.min())
        choch=bool(bos)
        ema_confirm=(sweep_dir=="BUY" and price>ema13[i]) or (sweep_dir=="SELL" and price<ema13[i])
        regime="RANGE"
        slope=ema50[i]-ema50[max(0,i-5)]
        relvol=atr[i]/price if np.isfinite(atr[i]) and price else 0
        if relvol>.003: regime="HIGH_VOLATILITY"
        elif relvol<.0008: regime="LOW_VOLATILITY"
        elif price>ema50[i] and slope>0: regime="STRONG_UPTREND" if slope>price*.001 else "UPTREND"
        elif price<ema50[i] and slope<0: regime="STRONG_DOWNTREND" if abs(slope)>price*.001 else "DOWNTREND"
        future=df.iloc[i+1:i+1+horizon_bars]
        if sweep_dir=="BUY":
            fret=float(future.iloc[-1].close)-price; mfe=float(future.high.max())-price; mae=price-float(future.low.min())
        elif sweep_dir=="SELL":
            fret=price-float(future.iloc[-1].close); mfe=price-float(future.low.min()); mae=float(future.high.max())-price
        else:
            fret=float(future.iloc[-1].close)-price; mfe=float(future.high.max())-price; mae=price-float(future.low.min())
        opposite=buy_level if sweep_dir=="SELL" else sell_level
        rows.append({"timestamp":df.index[i],"symbol":config.symbol,"timeframe":config.entry_timeframe,"close":price,
          "nearest_buy_liquidity":buy_level,"nearest_sell_liquidity":sell_level,"nearest_opposite_liquidity":opposite,
          "liquidity_swept":swept,"sweep":swept,"sweep_direction":sweep_dir,"sweep_strength":"CONFIRMED" if swept else "NONE",
          "sweep_overshoot":overshoot,"displacement_strength":disp,"displacement":disp,"bos":bool(bos),"choch":choch,
          "ema13_confirmation":bool(ema_confirm),"mtf_alignment":bool((sweep_dir=="BUY" and price>ema50[i]) or (sweep_dir=="SELL" and price<ema50[i])),
          "regime":regime,"session":"ASIA" if df.index[i].hour<7 else "LONDON" if df.index[i].hour<13 else "OVERLAP" if df.index[i].hour<17 else "NEW_YORK" if df.index[i].hour<22 else "OFF_SESSION",
          "feature_version":config.liquidity_flow.feature_version,"future_return":fret,"mfe":mfe,"mae":mae,
          "hit_target":bool(mfe>config.point_size*100),"hit_stop":bool(mae>config.point_size*100),"horizon_bars":horizon_bars})
    return pd.DataFrame(rows)


def save_dataset(dataset: pd.DataFrame, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(path, index=False)
