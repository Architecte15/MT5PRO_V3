from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict

import pandas as pd


@dataclass
class DataCache:
    frames: Dict[str, pd.DataFrame] | None = None

    def __post_init__(self) -> None:
        if self.frames is None:
            self.frames = {}

    def put(self, key: str, df: pd.DataFrame) -> None:
        self.frames[key] = df.copy()

    def get(self, key: str) -> pd.DataFrame | None:
        df = self.frames.get(key)
        return None if df is None else df.copy()

    def append(self, key: str, new_df: pd.DataFrame) -> pd.DataFrame:
        old = self.frames.get(key)
        if old is None:
            merged = new_df.copy()
        else:
            merged = pd.concat([old, new_df]).sort_index()
            merged = merged[~merged.index.duplicated(keep="last")]
        self.frames[key] = merged
        return merged.copy()

    def latest_timestamp(self, key: str) -> datetime | None:
        df = self.frames.get(key)
        if df is None or df.empty:
            return None
        ts = df.index.max()
        return ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
