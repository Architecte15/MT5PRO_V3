"""Liquidity Flow research runner (spec sections 17-18).

Pre-registered experiments H1-H8 + ablations A1/A2, evaluated with
chronological train/validation/OOS/holdout splits, walk-forward folds,
bootstrap confidence intervals and random controls (plus the current engine
as a third, informational reference).

STRICTLY OFFLINE: reads CSV data only. Never connects to MT5, never touches
the live engine, and cannot auto-deploy anything — the only output is a
report plus per-hypothesis trade logs for audit.

Usage:
    python -m scripts.run_liquidity_research [--control-draws N] [--skip-dataset]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app.research import evaluation as ev
from app.research.dataset import build_observations
from app.research.displacement import (
    ORDER as DISP_ORDER,
    DisplacementParams,
    measure_displacement,
)
from app.research.entries import (
    compute_sl,
    compute_tp,
    nearest_opposite_liquidity,
    simulate_trade,
)
from app.research.experiments import (
    ABLATIONS,
    DISPLACEMENT_GRID,
    DISPLACEMENT_SELECTION_RULE,
    HYPOTHESES,
    PROTOCOL,
    Hypothesis,
)
from app.research.features import bar_features
from app.research.regime import classify_regimes, classify_volatility, fit_volatility_thresholds
from app.research.sweeps import SWEEP_CONFIRMED, SWEEP_WEAK, detect_sweeps
from app.research.structure import detect_structure_events
from app.research.zones import map_liquidity_zones
from app.strategy.indicators import ema
from app.strategy.market_structure import detect_swings

ROOT = Path(__file__).resolve().parents[1]
M15_PATH = ROOT / "backtests" / "datasets" / "EURUSD_M15.csv"
H4_PATH = ROOT / "backtests" / "datasets" / "EURUSD_H4.csv"
BASELINE_TRADES = ROOT / "backtests" / "reports" / "trades.csv"
REPORT_DIR = ROOT / "research" / "reports"
DATASET_DIR = ROOT / "research" / "datasets"

POINT = 0.00001
BUFFER = PROTOCOL["sl_buffer_points"] * POINT
HORIZON = PROTOCOL["horizon_bars"]
ATR_MULT = PROTOCOL["atr_mult"]
WF_FOLDS = PROTOCOL["walk_forward_folds"]
MIN_TRADES = PROTOCOL["min_trades_oos"]
SWEEP_RANK = {SWEEP_WEAK: 1, SWEEP_CONFIRMED: 2}
DEFAULT_GRID_INDEX = 1          # DISPLACEMENT_GRID[1] == DisplacementParams() defaults
USD_PER_PRICE_UNIT_001LOT = 1000.0   # 0.01 lot: price delta 0.0001 -> $0.10
HTF_STALENESS_MAX = pd.Timedelta(hours=8)


def load_frame(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=[0])
    df = df.rename(columns={df.columns[0]: "timestamp"}).set_index("timestamp")
    df.columns = [str(c).lower() for c in df.columns]
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df.sort_index()


# --------------------------------------------------------------------- context
@dataclass
class Ctx:
    df: pd.DataFrame
    h4: pd.DataFrame
    features: pd.DataFrame
    atr: pd.Series
    atr_arr: np.ndarray
    zones: list
    sweeps: list
    swings: list
    bos_up: np.ndarray
    bos_dn: np.ndarray
    bos_kind_at: dict
    ema13: np.ndarray
    close: np.ndarray
    open_: np.ndarray
    align_up: np.ndarray
    align_dn: np.ndarray
    regime: pd.Series
    vol_regime: pd.Series
    entry_hour: np.ndarray
    eligible: list
    n: int


def build_ctx() -> Ctx:
    df = load_frame(M15_PATH)
    h4 = load_frame(H4_PATH)
    print(f"[data] M15: {len(df)} bars  {df.index[0]} -> {df.index[-1]}")
    print(f"[data] H4 : {len(h4)} bars  {h4.index[0]} -> {h4.index[-1]}")

    features = bar_features(df)
    atr = features["atr"]
    atr_arr = atr.to_numpy(dtype=float)
    ema13 = features["ema13"].to_numpy(dtype=float)

    print("[zones] mapping M15 + H4 liquidity zones ...")
    zones_m15 = map_liquidity_zones(df, "M15")
    zones_h4 = map_liquidity_zones(h4, "H4")
    # H4 zones first: when an H4 level and its M15 twin pierce together, the
    # HTF attribution must win, otherwise H5 (require_htf_zone) measures a
    # residual instead of real HTF-liquidity sweeps.
    zones = zones_h4 + zones_m15
    print(f"[zones] {len(zones)} zones (H4={len(zones_h4)}, M15={len(zones_m15)})")

    print("[sweeps] detecting sweeps ...")
    sweeps = detect_sweeps(df, zones, atr)
    print(f"[sweeps] {len(sweeps)} events "
          f"(confirmed={sum(1 for s in sweeps if s.sweep_class == SWEEP_CONFIRMED)})")

    events = detect_structure_events(df)
    bos_up = np.array(sorted(e.index for e in events if e.direction == "UP"), dtype=int)
    bos_dn = np.array(sorted(e.index for e in events if e.direction == "DOWN"), dtype=int)
    bos_kind_at = {e.index: e.kind for e in events}
    print(f"[structure] {len(events)} BOS/CHOCH events")

    # --- HTF (H4) alignment available at each M15 decision close ------------
    h4_ema = ema(h4["close"], 200)
    avail = pd.DatetimeIndex(h4.index) + pd.Timedelta(hours=4)
    htf = pd.DataFrame(
        {"h4_close": h4["close"].to_numpy(dtype=float),
         "h4_ema": h4_ema.to_numpy(dtype=float),
         "rising": (h4_ema.diff() > 0).to_numpy(),
         "src": avail},
        index=avail,
    ).sort_index()
    dec = pd.DatetimeIndex(df.index) + pd.Timedelta(minutes=15)
    htf_at = htf.reindex(htf.index.union(dec)).ffill().reindex(dec)
    stale = (dec - htf_at["src"]) <= HTF_STALENESS_MAX
    stale = stale.fillna(False).to_numpy()
    h4c, h4e = htf_at["h4_close"].to_numpy(dtype=float), htf_at["h4_ema"].to_numpy(dtype=float)
    rising = htf_at["rising"].fillna(False).to_numpy(dtype=bool)
    finite = np.isfinite(h4e)
    with np.errstate(invalid="ignore"):
        align_up = (h4c > h4e) & rising & stale & finite
        align_dn = (h4c < h4e) & (~rising) & stale & finite

    regime = classify_regimes(df, atr)
    t0, t1 = df.index[0], df.index[-1]
    b1 = t0 + (t1 - t0) * 0.6
    vol_hi, vol_lo = fit_volatility_thresholds(features["atr_pct"].loc[:b1])
    vol_regime = classify_volatility(features["atr_pct"], vol_hi, vol_lo)

    eligible = [i for i in range(30, len(df) - HORIZON) if atr_arr[i] == atr_arr[i]]

    return Ctx(
        df=df, h4=h4, features=features, atr=atr, atr_arr=atr_arr,
        zones=zones, sweeps=sweeps, swings=detect_swings(df, 2),
        bos_up=bos_up, bos_dn=bos_dn, bos_kind_at=bos_kind_at,
        ema13=ema13, close=df["close"].to_numpy(dtype=float),
        open_=df["open"].to_numpy(dtype=float),
        align_up=align_up, align_dn=align_dn,
        regime=regime, vol_regime=vol_regime,
        entry_hour=pd.DatetimeIndex(df.index).hour.to_numpy(),
        eligible=eligible, n=len(df),
    )


# ------------------------------------------------------------------ build runs
def _find_bos(ctx: Ctx, lo: int, hi: int, direction: int, kinds: tuple[str, ...]):
    arr = ctx.bos_up if direction > 0 else ctx.bos_dn
    k = int(np.searchsorted(arr, lo, side="left"))
    while k < len(arr) and int(arr[k]) <= hi:
        idx = int(arr[k])
        if ctx.bos_kind_at.get(idx) in kinds:
            return idx, ctx.bos_kind_at[idx]
        k += 1
    return None


def build_trades(
    ctx: Ctx,
    hyp: Hypothesis,
    disp_params: DisplacementParams,
    sl_override: str | None = None,
    tp_override: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    sl_mode = sl_override or hyp.sl_mode
    tp_mode = tp_override or hyp.tp_mode
    rank_min = SWEEP_RANK[hyp.min_sweep_class]
    stats = {
        "sweeps_in": len(ctx.sweeps), "skip_class": 0, "skip_htf_zone": 0,
        "skip_displacement": 0, "skip_bos": 0, "skip_ema13": 0, "skip_htf_align": 0,
        "skip_tail": 0, "skip_sl": 0, "skip_no_tp": 0, "skip_sim": 0, "built": 0,
    }
    rows: list[dict] = []

    for sev in ctx.sweeps:
        if SWEEP_RANK[sev.sweep_class] < rank_min:
            stats["skip_class"] += 1
            continue
        if hyp.require_htf_zone and sev.zone_timeframe != "H4":
            stats["skip_htf_zone"] += 1
            continue
        direction = 1 if sev.zone_type == "SELL_SIDE" else -1

        sig = sev.index
        disp_label, run_atr = "", float("nan")
        if hyp.require_displacement_at_least:
            disp_label, metrics = measure_displacement(
                ctx.df, ctx.atr_arr, sev.index, direction, disp_params)
            if DISP_ORDER[disp_label] < DISP_ORDER[hyp.require_displacement_at_least]:
                stats["skip_displacement"] += 1
                continue
            run_atr = metrics.get("run_atr", float("nan"))
            sig = sev.index + disp_params.window

        bos_kind = ""
        if hyp.require_bos_window:
            found = _find_bos(ctx, sev.index, sev.index + hyp.require_bos_window,
                              direction, hyp.require_bos_kinds)
            if found is None:
                stats["skip_bos"] += 1
                continue
            bos_index, bos_kind = found
            sig = max(sig, bos_index)

        if sig >= ctx.n - 1:
            stats["skip_tail"] += 1
            continue

        if hyp.require_ema13_close:
            e13 = ctx.ema13[sig]
            c = ctx.close[sig]
            if not (e13 == e13) or (direction > 0 and not c > e13) or (direction < 0 and not c < e13):
                stats["skip_ema13"] += 1
                continue

        if hyp.require_htf_trend_align:
            if not (ctx.align_up[sig] if direction > 0 else ctx.align_dn[sig]):
                stats["skip_htf_align"] += 1
                continue

        entry_open = float(ctx.open_[sig + 1])
        a = ctx.atr_arr[sig]
        sl = compute_sl(sl_mode, ctx.df, sig, direction, BUFFER,
                        atr_value=(float(a) if a == a and a > 0 else 0.0),
                        atr_mult=ATR_MULT, sweep_index=sev.index, swings=ctx.swings,
                        swing_strength=2, entry_price=entry_open)
        if sl is None:
            stats["skip_sl"] += 1
            continue

        decision_close = ctx.df.index[sig] + pd.Timedelta(minutes=15)
        if tp_mode == "TIME_EXIT":
            tp = None
        elif tp_mode == "OPPOSITE_LIQUIDITY":
            zone = nearest_opposite_liquidity(ctx.zones, direction, entry_open,
                                              decision_close, min_distance=BUFFER)
            if zone is None:
                stats["skip_no_tp"] += 1
                continue
            tp = float(zone.price)
        else:
            tp = compute_tp(tp_mode, direction, entry_open, sl, hyp.rr)

        result = simulate_trade(ctx.df, sig, direction, sl, tp, HORIZON)
        if not result:
            stats["skip_sim"] += 1
            continue

        stats["built"] += 1
        rows.append({
            "hypothesis": hyp.id,
            "signal_index": sig,
            "sweep_index": sev.index,
            "direction": direction,
            "entry_time": result["entry_time"],
            "exit_time": result["exit_time"],
            "entry": result["entry"], "exit": result["exit"],
            "sl": result["sl"], "tp": result["tp"],
            "pnl": result["pnl"], "reason": result["reason"],
            "bars_held": result["bars_held"],
            "mfe": result["mfe"], "mae": result["mae"],
            "sl_mode": sl_mode, "tp_mode": tp_mode,
            "sweep_class": sev.sweep_class,
            "zone_type": sev.zone_type, "zone_timeframe": sev.zone_timeframe,
            "zone_level": sev.level, "pierce_atr": sev.atr_rel,
            "sweep_trend_before": sev.trend_before,
            "displacement": disp_label, "displacement_run_atr": run_atr,
            "structure_break": bos_kind,
            "htf_aligned": bool(ctx.align_up[sig] if direction > 0 else ctx.align_dn[sig]),
            "regime": ctx.regime.iloc[sig],
            "volatility": ctx.vol_regime.iloc[sig],
            "entry_hour": int(ctx.entry_hour[sig + 1]),
        })
    trades = pd.DataFrame(rows)
    if len(trades):
        trades = trades.sort_values("entry_time").reset_index(drop=True)
    else:
        trades = pd.DataFrame(columns=[
            "hypothesis", "signal_index", "sweep_index", "direction", "entry_time",
            "exit_time", "entry", "exit", "sl", "tp", "pnl", "reason", "bars_held",
            "mfe", "mae", "sl_mode", "tp_mode", "sweep_class", "zone_type",
            "zone_timeframe", "zone_level", "pierce_atr", "sweep_trend_before",
            "displacement", "displacement_run_atr", "structure_break", "htf_aligned",
            "regime", "volatility", "entry_hour",
        ])
    return trades, stats


def tune_displacement(ctx: Ctx, hyp: Hypothesis) -> tuple[int, list[dict]]:
    """Grid search on TRAIN only; pre-registered selection rule; returns (idx, trials)."""
    trials: list[dict] = []
    candidates: list[tuple[int, float]] = []   # (grid_idx, train_expectancy)
    for gi, params in enumerate(DISPLACEMENT_GRID):
        trades, _ = build_trades(ctx, hyp, params)
        if len(trades):
            masks, _ = ev.time_split_masks(trades["entry_time"])
            tr = ev.trade_metrics(trades[masks["train"]])
        else:
            tr = ev.trade_metrics(pd.DataFrame())
        trials.append({"grid_index": gi, "params": asdict(params),
                       "train_n": tr["n"], "train_expectancy": tr["expectancy"]})
        if tr["n"] >= PROTOCOL["min_train_trades_for_grid_selection"]:
            candidates.append((gi, tr["expectancy"]))
    if not candidates:
        return DEFAULT_GRID_INDEX, trials
    best = max(c[1] for c in candidates)
    tied = [gi for gi, e in candidates if e >= best - 1e-12]
    if DEFAULT_GRID_INDEX in tied:
        return DEFAULT_GRID_INDEX, trials
    return tied[0], trials


# ------------------------------------------------------------------ evaluation
def _metrics_pack(sub: pd.DataFrame) -> dict:
    m = ev.trade_metrics(sub)
    ci = ev.bootstrap_ci(sub["pnl"]) if len(sub) else (float("nan"), float("nan"))
    m["expectancy_ci95"] = [ci[0], ci[1]]
    m["expectancy_usd_001lot"] = m["expectancy"] * USD_PER_PRICE_UNIT_001LOT
    return m


def evaluate_hypothesis(ctx: Ctx, hyp: Hypothesis, trades: pd.DataFrame,
                        stats: dict, control_draws: int) -> dict:
    entry_times = trades["entry_time"] if len(trades) else pd.Series(
        [], dtype="datetime64[ns, UTC]")
    masks, boundaries = ev.time_split_masks(entry_times)
    splits = {name: _metrics_pack(trades[mask]) for name, mask in masks.items()}

    wf_detail, wf_pos, wf_valid = [], 0, 0
    if len(trades):
        for tr_m, te_m, name in ev.walk_forward_masks(entry_times, folds=WF_FOLDS):
            m = ev.trade_metrics(trades[te_m])
            if m["n"] >= 5:
                wf_valid += 1
                if m["expectancy"] > 0:
                    wf_pos += 1
            wf_detail.append({"fold": name, "n": m["n"],
                              "expectancy": m["expectancy"], "pf": m["profit_factor"]})

    controls: dict = {}
    control_max = float("nan")
    oos = trades[masks["oos"]]
    oos_exp = splits["oos"]["expectancy"]
    if len(oos):
        rd = [ev.random_direction_control(oos, ctx.df, ctx.atr, PROTOCOL["rr"], HORIZON,
                                          ATR_MULT, BUFFER, seed=PROTOCOL["control_seed"] + d)
              for d in range(control_draws)]
        re_ = ev.random_eligible_control(ctx.df, ctx.atr, ctx.eligible, n=len(oos),
                                         rr=PROTOCOL["rr"], horizon=HORIZON,
                                         atr_mult=ATR_MULT, buffer_=BUFFER,
                                         seed=PROTOCOL["control_seed"], draws=control_draws)
        rd_s = ev.control_summary(rd, oos_exp)
        re_s = ev.control_summary(re_, oos_exp)
        controls = {"random_direction": rd_s, "random_eligible_entry": re_s}
        vals = [v for v in (rd_s["mean_expectancy"], re_s["mean_expectancy"]) if v == v]
        control_max = max(vals) if vals else float("nan")
    else:
        controls = {"note": "no OOS trades — controls not run"}

    verdict_str, reasons = ev.verdict(splits["oos"], tuple(splits["oos"]["expectancy_ci95"]),
                                      wf_pos, wf_valid, control_max, MIN_TRADES)
    # Post-hoc diagnostic (NOT part of the pre-registered verdict policy):
    # flags a "candidate" whose edge lives only in the most recent period.
    total_pnl = float(trades["pnl"].sum()) if len(trades) else 0.0
    train_pf = splits["train"]["profit_factor"]
    val_pf = splits["validation"]["profit_factor"]
    stale_early = ((splits["train"]["n"] > 0 and train_pf == train_pf and train_pf < 1.0)
                   or (splits["validation"]["n"] > 0 and val_pf == val_pf and val_pf < 1.0))
    diagnostics = {
        "posthoc_not_preregistered": True,
        "total_pnl_all_splits": total_pnl,
        "train_pf": train_pf,
        "validation_pf": val_pf,
        "holdout_pf": splits["holdout"]["profit_factor"],
        "flag": ("STABILITY_CONCERN: train/validation PF < 1 — edge concentrated in the "
                 "most recent period, likely regime; deployment NOT recommended"
                 if stale_early else "no early-split concern"),
    }
    return {
        "hypothesis": asdict(hyp),
        "n_total": int(len(trades)),
        "funnel": stats,
        "diagnostics_posthoc": diagnostics,
        "split_boundaries": {k: v for k, v in boundaries.items()},
        "splits": splits,
        "walk_forward": {"folds": wf_detail, "positive": wf_pos, "valid": wf_valid},
        "controls": controls,
        "control_max_expectancy": control_max,
        "verdict": verdict_str,
        "verdict_reasons": reasons,
        "by_regime": _slice_stats(trades, "regime"),
        "by_displacement": _slice_stats(trades, "displacement"),
        "by_sweep_trend": _slice_stats(trades, "sweep_trend_before"),
        "sample_trades": trades.head(3).to_dict("records") + trades.tail(3).to_dict("records")
        if len(trades) else [],
    }


def _slice_stats(trades: pd.DataFrame, col: str) -> dict:
    if not len(trades) or col not in trades.columns:
        return {}
    out = {}
    for key, sub in trades.groupby(col):
        m = ev.trade_metrics(sub)
        out[str(key)] = {"n": m["n"], "expectancy": m["expectancy"], "pf": m["profit_factor"],
                         "win_rate": m["win_rate"]}
    return out


def run_ablation(ctx: Ctx, abl, base_hyp: Hypothesis, base_params: DisplacementParams,
                 base_trades: pd.DataFrame) -> dict:
    out = {}
    for val in abl.values:
        sl_ov = val if abl.variant_field == "sl_mode" else None
        tp_ov = val if abl.variant_field == "tp_mode" else None
        eff_sl = sl_ov or base_hyp.sl_mode
        eff_tp = tp_ov or base_hyp.tp_mode
        if eff_sl == base_hyp.sl_mode and eff_tp == base_hyp.tp_mode:
            trades, stats = base_trades, {"note": "identique au build H2 de base"}
        else:
            trades, stats = build_trades(ctx, base_hyp, base_params, sl_ov, tp_ov)
        masks, _ = ev.time_split_masks(
            trades["entry_time"] if len(trades) else pd.Series([], dtype="datetime64[ns, UTC]"))
        out[val] = {
            "n_total": int(len(trades)),
            "overall": _metrics_pack(trades),
            "oos": _metrics_pack(trades[masks["oos"]]),
            "funnel": stats,
        }
    return {"base_hypothesis": abl.base, "variant_field": abl.variant_field,
            "report_only": True,
            "note": "Ablation: aucune variante n'est adoptée automatiquement (spec §9-§10).",
            "variants": out}


def baseline_current_engine() -> dict:
    if not BASELINE_TRADES.exists():
        return {"available": False}
    bdf = pd.read_csv(BASELINE_TRADES)
    col = "pnl" if "pnl" in bdf.columns else ("profit" if "profit" in bdf.columns else None)
    if col is None:
        return {"available": False, "note": "no pnl/profit column"}
    pnl = bdf[col].astype(float)
    return {
        "available": True,
        "source": str(BASELINE_TRADES.relative_to(ROOT)),
        "n": int(len(pnl)),
        "expectancy": float(pnl.mean()),
        "expectancy_usd_001lot": float(pnl.mean()) * USD_PER_PRICE_UNIT_001LOT,
        "win_rate": float((pnl > 0).mean()),
        "note": "Référence informative : moteur courant avec filtres session/jour, "
                "échantillon et période différents — pas un contrôle équivalent.",
    }


# ---------------------------------------------------------------------- output
def _san(o):
    if o is None or isinstance(o, (bool, str, int)) and not isinstance(o, np.generic):
        return o
    if o is pd.NaT:
        return None
    if isinstance(o, dict):
        return {str(k): _san(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, np.ndarray)):
        return [_san(v) for v in o]
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        if math.isnan(f):
            return None
        if math.isinf(f):
            return "inf" if f > 0 else "-inf"
        return f
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    return str(o)


def write_markdown(report: dict, path: Path) -> None:
    L: list[str] = []
    meta = report["meta"]
    L.append("# Liquidity Flow — rapport de recherche (hypothèses pré-enregistrées)")
    L.append("")
    L.append(f"- Généré : {meta['generated_at']}")
    L.append(f"- Hash de pré-enregistrement (protocol + H1-H8 + ablations + grille) : `{meta['prereg_hash']}`")
    L.append(f"- Données : M15 {report['data']['m15_bars']} barres "
             f"({str(report['data']['m15_range'][0])[:10]} → {str(report['data']['m15_range'][1])[:10]}), "
             f"H4 {report['data']['h4_bars']} barres")
    L.append(f"- Splits chronologiques : train 60% / validation 20% / OOS 10% / holdout 10% (dans le temps des trades)")
    L.append(f"- Détection sweeps : {report['data']['n_sweeps']} événements "
             f"({report['data']['n_confirmed']} confirmés)")
    L.append("")
    L.append("> Aucun composant n'est ajouté au moteur live. Ce document est un rapport, "
             "pas une autorisation de déploiement (spec §12-§18).")
    L.append("")
    L.append("## Verdicts")
    L.append("")
    L.append("| Hyp | Titre | n | OOS n | OOS espérance | OOS IC95 | OOS PF | WF + | Meilleur contrôle | VERDICT |")
    L.append("|---|---|--:|--:|--:|---|--:|--:|--:|---|")
    for hid, h in report["hypotheses"].items():
        oos = h["splits"]["oos"]
        ci = oos["expectancy_ci95"]
        ci_s = f"[{ci[0]:.6f}, {ci[1]:.6f}]" if ci[0] is not None else "n/a"
        pf = oos["profit_factor"]
        pf_s = f"{pf:.2f}" if isinstance(pf, float) else str(pf)
        cm = h["control_max_expectancy"]
        cm_s = f"{cm:.6f}" if isinstance(cm, float) else "n/a"
        wf = h["walk_forward"]
        L.append(f"| {hid} | {h['hypothesis']['title']} | {h['n_total']} | {oos['n']} "
                 f"| {oos['expectancy']:.6f} | {ci_s} | {pf_s} "
                 f"| {wf['positive']}/{wf['valid']} | {cm_s} | **{h['verdict']}** |")
    L.append("")

    for hid, h in report["hypotheses"].items():
        L.append(f"## {hid} — {h['hypothesis']['title']}")
        L.append("")
        L.append(f"- Composants : {', '.join(h['hypothesis']['components'])}")
        L.append(f"- SL : `{h['hypothesis']['sl_mode']}` | TP : `{h['hypothesis']['tp_mode']}` | RR : {h['hypothesis']['rr']}")
        f = h["funnel"]
        L.append(f"- Funnel : sweeps {f['sweeps_in']} → classe {f['skip_class']} écartés → "
                 f"zone HTF {f['skip_htf_zone']} → displacement {f['skip_displacement']} → "
                 f"BOS {f['skip_bos']} → EMA13 {f['skip_ema13']} → align HTF {f['skip_htf_align']} → "
                 f"SL {f['skip_sl']} → TP {f['skip_no_tp']} → simulation {f['skip_sim']} → "
                 f"**construits {f['built']}**")
        L.append(f"- Verdict : **{h['verdict']}**")
        for r in h["verdict_reasons"]:
            L.append(f"  - {r}")
        d = h.get("diagnostics_posthoc", {})
        L.append(f"- Diagnostic post-hoc (non pré-enregistré) : somme PnL tous splits = "
                 f"{d.get('total_pnl_all_splits', 0):.6f} | PF train={d.get('train_pf')} "
                 f"| PF validation={d.get('validation_pf')} | PF holdout={d.get('holdout_pf')} "
                 f"→ **{d.get('flag', '')}**")
        L.append("")
        L.append("| Split | n | Espérance (prix) | Espérance ~USD (0,01 lot) | IC95 | PF | WR | Max DD |")
        L.append("|---|--:|--:|--:|---|--:|--:|--:|")
        for name, m in h["splits"].items():
            ci = m["expectancy_ci95"]
            ci_s = (f"[{ci[0]:.6f}, {ci[1]:.6f}]" if ci[0] is not None else "n/a")
            pf = m["profit_factor"]
            pf_s = f"{pf:.2f}" if isinstance(pf, float) else str(pf)
            L.append(f"| {name} | {m['n']} | {m['expectancy']:.6f} "
                     f"| {m['expectancy_usd_001lot']:.2f} | {ci_s} | {pf_s} "
                     f"| {m['win_rate']:.1%} | {m['max_drawdown']:.6f} |")
        L.append("")
        if h["controls"]:
            L.append(f"- Contrôles (OOS) : `{json.dumps(_san(h['controls']))}`")
        wf = h["walk_forward"]
        wf_txt = ", ".join(
            f"{f['fold']} n={f['n']} esp={f['expectancy']:.6f}" for f in wf["folds"]) or "aucun"
        L.append(f"- Walk-forward : {wf_txt}")
        L.append("")
        if h["by_regime"]:
            L.append(f"- Par régime : `{json.dumps(_san(h['by_regime']))}`")
            L.append("")

    if report.get("ablations"):
        L.append("## Ablations (rapport seul — aucune adoption automatique)")
        L.append("")
        for aid, a in report["ablations"].items():
            L.append(f"### {aid} — {a['variant_field']} sur l'entrée « {a['base_hypothesis']} »")
            L.append("")
            L.append("| Variante | n | Espérance (prix) | PF | WR | OOS n | OOS espérance |")
            L.append("|---|--:|--:|--:|--:|--:|--:|")
            for val, r in a["variants"].items():
                m, o = r["overall"], r["oos"]
                pf = m["profit_factor"]
                pf_s = f"{pf:.2f}" if isinstance(pf, float) else str(pf)
                L.append(f"| `{val}` | {m['n']} | {m['expectancy']:.6f} | {pf_s} "
                         f"| {m['win_rate']:.1%} | {o['n']} | {o['expectancy']:.6f} |")
            L.append("")

    if report.get("displacement_tuning"):
        L.append("## Réglage de la grille displacement (TRAIN uniquement)")
        L.append("")
        L.append(f"Règle pré-enregistrée : {DISPLACEMENT_SELECTION_RULE}")
        L.append("")
        for hid, t in report["displacement_tuning"].items():
            L.append(f"- **{hid}** — choisi : grille #{t['chosen_index']} "
                     f"`{json.dumps(_san(t['chosen_params']))}`")
            for trial in t["trials"]:
                L.append(f"  - grille #{trial['grid_index']} `{json.dumps(_san(trial['params']))}` "
                         f"→ train n={trial['train_n']}, espérance={trial['train_expectancy']:.6f}")
        L.append("")

    L.append("## Référence : moteur courant")
    L.append("")
    L.append(f"`{json.dumps(_san(report['baseline_current_engine']))}`")
    L.append("")
    L.append("## Notes et limites (honnêteté du rapport)")
    L.append("")
    for note in report["notes"]:
        L.append(f"- {note}")
    L.append("")
    path.write_text("\n".join(L), encoding="utf-8")


# ------------------------------------------------------------------------ main
def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Liquidity Flow pre-registered research runner")
    ap.add_argument("--control-draws", type=int, default=PROTOCOL["control_draws"])
    ap.add_argument("--skip-dataset", action="store_true",
                    help="skip the per-candle observation dataset build (section 11)")
    args = ap.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    DATASET_DIR.mkdir(parents=True, exist_ok=True)

    prereg = {
        "protocol": PROTOCOL,
        "hypotheses": [asdict(h) for h in HYPOTHESES],
        "ablations": [asdict(a) for a in ABLATIONS],
        "displacement_grid": [asdict(g) for g in DISPLACEMENT_GRID],
        "displacement_selection_rule": DISPLACEMENT_SELECTION_RULE,
    }
    prereg_hash = ev.hash_preregistration(prereg)
    print(f"[prereg] hash = {prereg_hash}")

    ctx = build_ctx()

    # ---- hypotheses -------------------------------------------------------
    tuning: dict = {}
    hyp_results: dict = {}
    for hyp in HYPOTHESES:
        print(f"[{hyp.id}] {hyp.title} ...")
        if hyp.require_displacement_at_least:
            gi, trials = tune_displacement(ctx, hyp)
            params = DISPLACEMENT_GRID[gi]
            tuning[hyp.id] = {"chosen_index": gi, "chosen_params": asdict(params),
                              "trials": trials,
                              "selection_rule": DISPLACEMENT_SELECTION_RULE}
        else:
            params = DISPLACEMENT_GRID[DEFAULT_GRID_INDEX]
        trades, stats = build_trades(ctx, hyp, params)
        trades.to_csv(REPORT_DIR / f"liquidity_trades_{hyp.id}.csv", index=False)
        hyp_results[hyp.id] = evaluate_hypothesis(ctx, hyp, trades, stats, args.control_draws)
        v = hyp_results[hyp.id]
        oos = v["splits"]["oos"]
        print(f"[{hyp.id}] n={v['n_total']} (OOS {oos['n']}) "
              f"OOS esp={oos['expectancy']:.6f} → {v['verdict']}")
        if hyp.id == "H2":
            h2_trades, h2_params = trades, params

    # ---- ablations --------------------------------------------------------
    ablations_out = {}
    base_hyp = next(h for h in HYPOTHESES if h.id == "H2")
    for abl in ABLATIONS:
        print(f"[{abl.id}] {abl.title} ...")
        ablations_out[abl.id] = run_ablation(ctx, abl, base_hyp, h2_params, h2_trades)

    # ---- observation dataset (section 11) --------------------------------
    dataset_info: dict = {"built": False}
    if not args.skip_dataset:
        print("[dataset] building per-candle observations (section 11) ...")
        obs = build_observations(ctx.df, ctx.features, ctx.zones, ctx.sweeps, ctx.atr,
                                 horizon=HORIZON)
        out_csv = DATASET_DIR / "observations_eurusd_m15.csv"
        obs.to_csv(out_csv)
        dataset_info = {"built": True, "rows": int(len(obs)),
                        "columns": list(obs.columns),
                        "path": str(out_csv.relative_to(ROOT))}
        print(f"[dataset] {len(obs)} rows -> {dataset_info['path']}")

    sweeps_df = pd.DataFrame([{
        "index": s.index, "timestamp": s.timestamp, "zone_id": s.zone_id,
        "zone_type": s.zone_type, "zone_tf": s.zone_timeframe, "level": s.level,
        "pierce": s.pierce_distance, "atr_rel": s.atr_rel, "volume_rel": s.volume_rel,
        "closed_back": s.closed_back, "reentry_bars": s.reentry_bars,
        "sweep_class": s.sweep_class, "trend_before": s.trend_before,
        "momentum_before": s.momentum_before, "displacement": s.displacement,
    } for s in ctx.sweeps])
    sweeps_df.to_csv(REPORT_DIR / "liquidity_sweeps.csv", index=False)

    report = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "prereg_hash": prereg_hash,
            "protocol": PROTOCOL,
            "displacement_selection_rule": DISPLACEMENT_SELECTION_RULE,
            "control_draws": args.control_draws,
            "runner": "scripts/run_liquidity_research.py",
            "live_engine_modified": False,
        },
        "data": {
            "m15_bars": int(len(ctx.df)),
            "m15_range": [ctx.df.index[0], ctx.df.index[-1]],
            "h4_bars": int(len(ctx.h4)),
            "h4_range": [ctx.h4.index[0], ctx.h4.index[-1]],
            "n_zones": len(ctx.zones),
            "n_sweeps": len(ctx.sweeps),
            "n_confirmed": sum(1 for s in ctx.sweeps if s.sweep_class == SWEEP_CONFIRMED),
            "n_structure_events": len(ctx.bos_up) + len(ctx.bos_dn),
            "eligible_signal_bars": len(ctx.eligible),
        },
        "hypotheses": hyp_results,
        "displacement_tuning": tuning,
        "ablations": ablations_out,
        "baseline_current_engine": baseline_current_engine(),
        "dataset": dataset_info,
        "notes": [
            "Module strictement parallèle : app/research n'est importé par aucun code live "
            "(app.main / TradingEngine / SignalEngine inchangés).",
            "Aucune hypothèse n'est déployée automatiquement : un verdict CANDIDATE exige "
            "revue du holdout + approbation manuelle (spec §12 : MODEL VERSION, rollback).",
            "§19 binaires : N/A — ce bot exécute du spot MT5. formule BE_WR = LOSS/(WIN+LOSS) "
            "disponible dans app.research.evaluation.breakeven_wr pour tout usage futur.",
            "Périodes d'entrée multi-TF : M15 (sweep/displacement/BOS/EMA13) + H4 (liquidité HTF, "
            "alignement). M5/H1 non disponibles sans pause de la boucle live (connexion MT5 "
            "exclusive) — expériences LTF reportées (spec §6).",
            "Seuils de displacement : grille pré-enregistrée, sélection sur TRAIN uniquement, "
            "figée avant validation/OOS/holdout (spec §4).",
            "Contrôles : RANDOM_DIRECTION (mêmes entrées, côté au hasard, stop ATR + 2R) et "
            "RANDOM_ELIGIBLE_ENTRY (dates au hasard dans l'ensemble éligible, mêmes règles "
            "neutres) ; BASELINE_CURRENT_ENGINE en référence informative. Ces contrôles "
            "utilisent un stop ATR neutre : battre RANDOM_DIRECTION avec un stop SWEEP_EXTREME "
            "peut refléter la qualité du placement de stop autant que celle du timing de direction.",
            "Diagnostics marqués « post-hoc » (somme PnL tous splits, PF train/validation) ne "
            "font PAS partie de la politique de verdict pré-enregistrée — ils informent la "
            "décision humaine sans la remplacer.",
            "Ablation H7 (post-hoc) : OPPOSITE_LIQUIDITY n'imposait qu'une distance minimale "
            "de 5 points à la cible → cibles quasi immédiates, WR ~90% mais PF OOS < 1. "
            "Toute révision (ex. distance min ≥ 1×ATR) devra être pré-enregistrée AVANT retest.",
            "Chevauchement de positions : ce backtest, comme le moteur, autorise les trades "
            "superposés alors que le live est à max_open_positions=1 — le sous-ensemble "
            "réalisable en live est plus petit que n_total.",
            "Composants reportés (non implémentés cette phase, par design contrôlé) : "
            "memory/similarité §14, drift §16, online learning §15, registre de modèles §12, "
            "sorties PARTIAL/RUNNER §10, régimes par symbole/session §13 (cellules trop "
            "petites sur un seul symètre — reportés).",
            "Métriques en unités de prix EURUSD ; conversion indicative USD @0,01 lot = prix × 1000 "
            "(spread et latence non inclus).",
            "Échantillons : un verdict de déploiement exige n_OOS ≥ 30, IC95 > 0, PF > 1, "
            "supériorité sur les deux contrôles et stabilité walk-forward ≥ 75%.",
        ],
    }

    json_path = REPORT_DIR / "liquidity_flow_report.json"
    md_path = REPORT_DIR / "liquidity_flow_report.md"
    json_path.write_text(json.dumps(_san(report), indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(report, md_path)

    print()
    print("=" * 78)
    print("RÉSUMÉ DES VERDICTS")
    print("=" * 78)
    for hid, h in hyp_results.items():
        oos = h["splits"]["oos"]
        print(f"  {hid}: n={h['n_total']:>4}  OOS n={oos['n']:>3}  "
              f"OOS esp={oos['expectancy']:>+.6f}  → {h['verdict']}")
    print("-" * 78)
    print(f"Rapport JSON : {json_path.relative_to(ROOT)}")
    print(f"Rapport MD   : {md_path.relative_to(ROOT)}")
    if dataset_info.get("built"):
        print(f"Dataset      : {dataset_info['path']} ({dataset_info['rows']} lignes)")
    print("Live engine  : NON MODIFIÉ (aucun import app.research côté live).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
