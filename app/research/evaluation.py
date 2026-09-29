"""Validation harness (spec section 18): chronological splits, bootstrap CIs,
walk-forward, random controls, and the EDGE NOT FOUND verdict policy.

Verdict policy (pre-registered in experiments.PROTOCOL):
    EDGE NOT FOUND if ANY of:
      - OOS trade count < min_trades_oos
      - 95% bootstrap CI of OOS expectancy includes 0
      - OOS profit factor <= 1
      - OOS expectancy <= both random controls
      - walk-forward positive folds < 75% of folds
    Otherwise: CANDIDATE — still requires holdout review + manual approval;
    automatic deployment is forbidden by design.
"""

from __future__ import annotations

import hashlib
import json
import math

import numpy as np
import pandas as pd

from app.research.entries import compute_sl, compute_tp, simulate_trade


# --------------------------------------------------------------------- splits

def time_split_masks(times: pd.Series) -> tuple[dict[str, np.ndarray], dict[str, pd.Timestamp]]:
    t = pd.to_datetime(pd.Series(times))
    t0, t1 = t.min(), t.max()
    span = t1 - t0
    b1 = t0 + span * 0.6
    b2 = t0 + span * 0.8
    b3 = t0 + span * 0.9
    masks = {
        "train": (t < b1).to_numpy(),
        "validation": ((t >= b1) & (t < b2)).to_numpy(),
        "oos": ((t >= b2) & (t < b3)).to_numpy(),
        "holdout": (t >= b3).to_numpy(),
    }
    boundaries = {"t0": t0, "train_end": b1, "validation_end": b2, "oos_end": b3, "t1": t1}
    return masks, boundaries


def walk_forward_masks(
    times: pd.Series,
    folds: int = 4,
    initial_train: float = 0.4,
    test_frac: float = 0.125,
) -> list[tuple[np.ndarray, np.ndarray, str]]:
    t = pd.to_datetime(pd.Series(times))
    t0, t1 = t.min(), t.max()
    span = t1 - t0
    out = []
    for k in range(folds):
        train_end = t0 + span * (initial_train + k * test_frac)
        test_end = t0 + span * (initial_train + (k + 1) * test_frac)
        if test_end > t1:
            break
        train_m = (t < train_end).to_numpy()
        test_m = ((t >= train_end) & (t < test_end)).to_numpy()
        out.append((train_m, test_m, f"fold{k + 1}"))
    return out


# -------------------------------------------------------------------- metrics

def bootstrap_ci(values, n_boot: int = 2000, ci: float = 0.95, seed: int = 1337) -> tuple[float, float]:
    v = np.asarray(list(values), dtype=float)
    v = v[~np.isnan(v)]
    if v.size == 0:
        return (float("nan"), float("nan"))
    if v.size == 1:
        return (float(v[0]), float(v[0]))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, v.size, size=(n_boot, v.size))
    means = v[idx].mean(axis=1)
    lo, hi = np.percentile(means, [(1 - ci) / 2 * 100, (1 + ci) / 2 * 100])
    return (float(lo), float(hi))


def trade_metrics(trades: pd.DataFrame) -> dict:
    if trades is None or len(trades) == 0:
        return {
            "n": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "expectancy": 0.0,
            "gross_profit": 0.0, "gross_loss": 0.0, "profit_factor": float("nan"),
            "payoff": 0.0, "max_drawdown": 0.0, "avg_mfe": 0.0, "avg_mae": 0.0,
            "avg_bars_held": 0.0, "sl_exits": 0, "tp_exits": 0, "time_exits": 0,
        }
    pnl = trades["pnl"].astype(float).to_numpy()
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gp = float(wins.sum())
    gl = float(-losses.sum())
    pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0.0)
    cum = np.cumsum(pnl)
    peak = np.maximum.accumulate(cum) if len(cum) else cum
    reasons = trades["reason"].value_counts().to_dict() if "reason" in trades else {}
    return {
        "n": int(len(pnl)),
        "wins": int((pnl > 0).sum()),
        "losses": int((pnl < 0).sum()),
        "win_rate": float((pnl > 0).mean()),
        "expectancy": float(pnl.mean()),
        "gross_profit": gp,
        "gross_loss": gl,
        "profit_factor": pf,
        "payoff": float(wins.mean() / abs(losses.mean())) if len(wins) and len(losses) else float("nan"),
        "max_drawdown": float(np.max(peak - cum)),
        "avg_mfe": float(trades["mfe"].mean()) if "mfe" in trades else float("nan"),
        "avg_mae": float(trades["mae"].mean()) if "mae" in trades else float("nan"),
        "avg_bars_held": float(trades["bars_held"].mean()) if "bars_held" in trades else float("nan"),
        "sl_exits": int(reasons.get("SL", 0)),
        "tp_exits": int(reasons.get("TP", 0)),
        "time_exits": int(reasons.get("TIME", 0)),
    }


def breakeven_wr(loss_per_trade: float, win_per_trade: float) -> float:
    """BE_WR = LOSS / (WIN + LOSS) — spec section 19 (binary payout, N/A to spot)."""
    denom = win_per_trade + loss_per_trade
    return loss_per_trade / denom if denom else float("nan")


# ------------------------------------------------------------------ controls

def random_direction_control(
    trades: pd.DataFrame, df: pd.DataFrame, atr: pd.Series,
    rr: float, horizon: int, atr_mult: float, buffer_: float, seed: int,
) -> np.ndarray:
    """Same entries, fair-coin side, neutral ATR stop + fixed RR target."""
    rng = np.random.default_rng(seed)
    pnls = []
    for _, row in trades.iterrows():
        signal_index = int(row["signal_index"])
        direction = int(rng.integers(0, 2)) * 2 - 1
        entry_open = float(df["open"].iloc[signal_index + 1])
        sl = compute_sl("ATR_BASED", df, signal_index, direction, buffer_,
                        atr_value=float(atr.iloc[signal_index]), atr_mult=atr_mult,
                        entry_price=entry_open)
        if sl is None:
            continue
        tp = compute_tp("FIXED_RR", direction, entry_open, sl, rr)
        result = simulate_trade(df, signal_index, direction, sl, tp, horizon)
        if result:
            pnls.append(result["pnl"])
    return np.asarray(pnls, dtype=float)


def random_eligible_control(
    df: pd.DataFrame, atr: pd.Series, eligible_signals: list[int],
    n: int, rr: float, horizon: int, atr_mult: float, buffer_: float, seed: int,
    draws: int = 100,
) -> list[np.ndarray]:
    """Random signals from the eligible opportunity set, neutral stops/targets."""
    out: list[np.ndarray] = []
    eligible = np.asarray(eligible_signals, dtype=int)
    if eligible.size == 0 or n <= 0:
        return out
    rng = np.random.default_rng(seed)
    for _ in range(draws):
        pick = rng.choice(eligible, size=min(n, eligible.size), replace=False)
        pnls = []
        for i in pick:
            i = int(i)
            direction = int(rng.integers(0, 2)) * 2 - 1
            entry_open = float(df["open"].iloc[i + 1])
            sl = compute_sl("ATR_BASED", df, i, direction, buffer_,
                            atr_value=float(atr.iloc[i]), atr_mult=atr_mult,
                            entry_price=entry_open)
            if sl is None:
                continue
            tp = compute_tp("FIXED_RR", direction, entry_open, sl, rr)
            result = simulate_trade(df, i, direction, sl, tp, horizon)
            if result:
                pnls.append(result["pnl"])
        out.append(np.asarray(pnls, dtype=float))
    return out


def control_summary(draws: list[np.ndarray], real_expectancy: float) -> dict:
    exps = np.array([d.mean() if d.size else np.nan for d in draws], dtype=float)
    exps = exps[~np.isnan(exps)]
    if exps.size == 0:
        return {"mean_expectancy": float("nan"), "share_draws_ge_real": float("nan"), "draws": 0}
    return {
        "mean_expectancy": float(exps.mean()),
        "p95_expectancy": float(np.percentile(exps, 95)),
        "share_draws_ge_real": float((exps >= real_expectancy).mean()),
        "draws": int(exps.size),
    }


# ------------------------------------------------------------------- verdict

def verdict(
    oos_metrics: dict,
    oos_ci: tuple[float, float],
    wf_positive: int,
    wf_folds: int,
    control_max_expectancy: float,
    min_trades: int,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if oos_metrics["n"] < min_trades:
        reasons.append(f"OOS n={oos_metrics['n']} < {min_trades}")
    if not (oos_ci[0] == oos_ci[0]) or oos_ci[0] <= 0:  # NaN or <= 0
        reasons.append(f"95% CI of OOS expectancy includes/below 0: {oos_ci}")
    if not (oos_metrics["profit_factor"] > 1):
        reasons.append(f"OOS PF={oos_metrics['profit_factor']}")
    if oos_metrics["expectancy"] <= control_max_expectancy:
        reasons.append(
            f"OOS expectancy {oos_metrics['expectancy']:.6f} <= best control {control_max_expectancy:.6f}"
        )
    if wf_folds == 0 or wf_positive / wf_folds < 0.75:
        reasons.append(f"walk-forward stability {wf_positive}/{wf_folds} < 75%")
    if reasons:
        return "EDGE NOT FOUND", reasons
    return "CANDIDATE (holdout + manual approval required; auto-deploy forbidden)", ["all gates passed"]


# ------------------------------------------------------------- prereg hashing

def hash_preregistration(payload: object) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]
