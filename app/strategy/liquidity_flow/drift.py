from __future__ import annotations

import pandas as pd
import numpy as np


def population_stability_index(expected: pd.Series, actual: pd.Series, bins: int = 10) -> float:
    e = pd.Series(expected).dropna().astype(float); a = pd.Series(actual).dropna().astype(float)
    if len(e) < bins or len(a) < bins: return float("nan")
    edges = np.unique(np.quantile(e, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3: return 0.0
    ep = np.histogram(e, bins=edges)[0] / len(e); ap = np.histogram(a.clip(edges[0], edges[-1]), bins=edges)[0] / len(a)
    ep = np.clip(ep, 1e-6, None); ap = np.clip(ap, 1e-6, None)
    return float(np.sum((ap-ep) * np.log(ap/ep)))


def drift_report(reference: pd.DataFrame, current: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    rows=[]
    for col in columns:
        if col not in reference or col not in current: continue
        psi=population_stability_index(reference[col], current[col])
        rows.append({"feature":col,"psi":psi,"status":"DRIFT_DETECTED" if np.isfinite(psi) and psi >= .25 else "STABLE"})
    return pd.DataFrame(rows)
