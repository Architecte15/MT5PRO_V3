from __future__ import annotations

from dataclasses import dataclass
import math
import pandas as pd
import numpy as np


@dataclass(frozen=True)
class ValidationSlice:
    name: str
    start: int
    end: int


def chronological_splits(n: int, train_ratio: float = .60, validation_ratio: float = .20, oos_ratio: float = .10) -> list[ValidationSlice]:
    if not (0 < train_ratio < 1 and 0 < validation_ratio < 1 and 0 < oos_ratio < 1 and train_ratio + validation_ratio + oos_ratio < 1):
        raise ValueError("Invalid chronological split ratios")
    a = int(n * train_ratio); b = int(n * (train_ratio + validation_ratio)); c = int(n * (train_ratio + validation_ratio + oos_ratio))
    return [ValidationSlice("TRAIN", 0, a), ValidationSlice("VALIDATION", a, b), ValidationSlice("OOS", b, c), ValidationSlice("FINAL_HOLDOUT", c, n)]


def bootstrap_ci(values: pd.Series | np.ndarray, alpha: float = .05, samples: int = 2000, seed: int = 42) -> tuple[float, float]:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    means = np.array([rng.choice(x, size=len(x), replace=True).mean() for _ in range(samples)])
    return float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def summarize_returns(df: pd.DataFrame, return_col: str = "future_return") -> dict[str, float | int | tuple[float, float]]:
    if df.empty:
        return {"n": 0, "expectancy": float("nan"), "win_rate": float("nan"), "ci95": (float("nan"), float("nan"))}
    x = df[return_col].astype(float)
    return {"n": int(len(x)), "expectancy": float(x.mean()), "win_rate": float((x > 0).mean()), "ci95": bootstrap_ci(x)}


def edge_status(train: pd.DataFrame, validation: pd.DataFrame, oos: pd.DataFrame, holdout: pd.DataFrame,
                min_samples: int = 100) -> dict[str, object]:
    """Conservative promotion gate; no model is promoted from in-sample performance alone."""
    summaries = {name: summarize_returns(part) for name, part in {
        "TRAIN": train, "VALIDATION": validation, "OOS": oos, "FINAL_HOLDOUT": holdout
    }.items()}
    required = [summaries[n]["n"] >= min_samples for n in ("TRAIN", "OOS", "FINAL_HOLDOUT")]
    positive = all(float(summaries[n]["expectancy"]) > 0 for n in ("VALIDATION", "OOS", "FINAL_HOLDOUT") if summaries[n]["n"])
    oos_ci = summaries["OOS"]["ci95"]
    holdout_ci = summaries["FINAL_HOLDOUT"]["ci95"]
    ci_supports_positive = (
        isinstance(oos_ci, tuple) and isinstance(holdout_ci, tuple)
        and all(pd.notna(x) for x in (*oos_ci, *holdout_ci))
        and oos_ci[0] > 0 and holdout_ci[0] > 0
    )
    if not all(required):
        status = "EDGE_NOT_ENOUGH_EVIDENCE"
    elif positive and ci_supports_positive:
        status = "EDGE_FOUND"
    else:
        status = "EDGE_NOT_FOUND"
    return {"status": status, "splits": summaries}
