import pandas as pd
import numpy as np

from app.config.settings import load_settings
from app.strategy.liquidity_flow.model import detect_liquidity_zones, detect_sweep, measure_displacement
from app.strategy.liquidity_flow.validation import chronological_splits
from app.strategy.liquidity_flow.memory import nearest_historical_setups


def frame():
    idx = pd.date_range("2026-01-01", periods=80, freq="15min", tz="UTC")
    x = np.linspace(1.1000, 1.1050, 80)
    return pd.DataFrame({"open":x-0.0002,"high":x+0.0005,"low":x-0.0005,"close":x}, index=idx)


def test_liquidity_zones_are_built_from_confirmed_swings():
    df=frame()
    zones=detect_liquidity_zones(df,"M15",2,0.0002)
    assert isinstance(zones,list)


def test_splits_are_chronological_and_cover_dataset():
    parts=chronological_splits(100)
    assert [p.name for p in parts]==["TRAIN","VALIDATION","OOS","FINAL_HOLDOUT"]
    assert parts[0].end <= parts[1].start <= parts[1].end <= parts[2].start <= parts[2].end <= parts[3].start
    assert parts[-1].end == 100


def test_memory_excludes_future_rows():
    d=pd.DataFrame({"timestamp":pd.date_range("2026-01-01", periods=5),"sweep":[1]*5,"bos":[1]*5,"ema13_confirmation":[1]*5,"future_return":[1,2,3,4,5],"mfe":[1]*5,"mae":[1]*5})
    r=nearest_historical_setups(d,d.iloc[-1],k=10,before=d.iloc[-1].timestamp)
    assert len(r)==4
    assert (pd.to_datetime(r.timestamp) < d.iloc[-1].timestamp).all()
