from __future__ import annotations

import numpy as np
import pandas as pd
from .validation import summarize_returns, chronological_splits, edge_status

HYPOTHESES = {
    "H1": ["sweep"],
    "H2": ["sweep", "displacement"],
    "H3": ["sweep", "displacement", "bos"],
    "H4": ["sweep", "displacement", "bos", "ema13_confirmation"],
    "H5": ["sweep", "displacement", "nearest_opposite_liquidity"],
    "H6": ["sweep", "displacement", "bos", "mtf_alignment"],
    "H7": ["opposite_liquidity_target"],
    "H8": ["sweep", "displacement", "bos", "mtf_alignment", "ema13_confirmation", "opposite_liquidity_target"],
}


def _mask(df: pd.DataFrame, components: list[str]) -> pd.Series:
    m = pd.Series(True, index=df.index)
    for c in components:
        if c in {"sweep", "bos", "ema13_confirmation", "mtf_alignment", "opposite_liquidity_target"}:
            if c not in df: return pd.Series(False, index=df.index)
            m &= df[c].astype(bool)
        elif c == "displacement":
            m &= df.get(c, pd.Series("NO_DISPLACEMENT", index=df.index)).isin(["MODERATE_DISPLACEMENT", "STRONG_DISPLACEMENT"])
        elif c == "nearest_opposite_liquidity":
            m &= df.get(c, pd.Series(False, index=df.index)).notna()
    return m


def run_experiments(dataset: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, components in HYPOTHESES.items():
        mask = _mask(dataset, components)
        candidate = dataset.loc[mask]
        s = summarize_returns(candidate)
        rows.append({"hypothesis": name, "components": "+".join(components), **s})
    controls = {
        "RANDOM_ELIGIBLE_ENTRY": dataset.sample(len(dataset), random_state=7) if len(dataset) else dataset,
        "BASELINE_CURRENT_ENGINE": dataset,
    }
    for name, candidate in controls.items():
        s = summarize_returns(candidate)
        rows.append({"hypothesis": name, "components": "CONTROL", **s})
    return pd.DataFrame(rows)


def walk_forward(dataset: pd.DataFrame, min_samples: int = 100) -> tuple[pd.DataFrame, dict[str, object]]:
    splits = chronological_splits(len(dataset))
    parts = {s.name: dataset.iloc[s.start:s.end] for s in splits}
    rows = [{"split": name, **summarize_returns(part)} for name, part in parts.items()]
    return pd.DataFrame(rows), edge_status(parts["TRAIN"], parts["VALIDATION"], parts["OOS"], parts["FINAL_HOLDOUT"], min_samples)
