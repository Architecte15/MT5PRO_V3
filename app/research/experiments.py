"""Pre-registered hypotheses and protocol (spec sections 17-18).

THIS FILE MUST EXIST BEFORE ANY RUN. The runner hashes its contents into the
report so results cannot retroactively change the question that was asked.

Frozen choices (declared up front, not after seeing outcomes):
- direction rule: reversion — sell-side swept -> BUY, buy-side swept -> SELL
  (the displacement/BOS components test continuation entry rules per spec ex.);
- signal on closed bar, entry at next open, SL buffer 5 points, RR 2.0,
  ATR SL multiplier 1.5, outcome horizon 96 M15 bars (24h);
- displacement threshold grid tuned on TRAIN ONLY with an explicit selection
  rule; everything else fixed;
- ablations A1/A2 are REPORT-ONLY: no variant is auto-adopted (spec section 9).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.research.displacement import (
    MODERATE_DISPLACEMENT,
    DisplacementParams,
)
from app.research.entries import (
    ATR_BASED,
    ENTRY_SIGNAL_CANDLE,
    STRUCTURE,
    SWEEP_EXTREME,
    TP_FIXED_RR,
    TP_OPPOSITE_LIQUIDITY,
    TP_TIME_EXIT,
)
from app.research.sweeps import SWEEP_CONFIRMED

PROTOCOL = {
    "hypothesis_version": "1.0",
    "feature_version": "11-obs-v1",
    "entry_rule": "signal on closed bar; fill at next open; SL-first if both touched",
    "direction_rule": "reversion: sell-side swept -> BUY; buy-side swept -> SELL",
    "sl_buffer_points": 5,
    "rr": 2.0,
    "atr_mult": 1.5,
    "horizon_bars": 96,
    "min_trades_oos": 30,
    "train_frac": 0.6,
    "val_frac": 0.2,
    "oos_frac": 0.1,
    "holdout_frac": 0.1,
    "walk_forward_folds": 4,
    "control_draws": 100,
    "control_seed": 1337,
    "min_train_trades_for_grid_selection": 15,
}

# Pre-registered displacement grid: tuned on TRAIN only (runner applies
# PROTOCOL["min_train_trades_for_grid_selection"] then freezes the choice).
DISPLACEMENT_GRID: tuple[DisplacementParams, ...] = (
    DisplacementParams(weak_atr=0.6, moderate_atr=0.8, strong_atr=1.2),
    DisplacementParams(weak_atr=0.6, moderate_atr=1.0, strong_atr=1.6),  # defaults
    DisplacementParams(weak_atr=0.8, moderate_atr=1.2, strong_atr=2.0),
)
DISPLACEMENT_SELECTION_RULE = (
    "max TRAIN expectancy among grid candidates with >= "
    f"{PROTOCOL['min_train_trades_for_grid_selection']} TRAIN trades; ties -> default params"
)


@dataclass(frozen=True)
class Hypothesis:
    id: str
    title: str
    components: tuple[str, ...]
    min_sweep_class: str = SWEEP_CONFIRMED
    require_displacement_at_least: str | None = None
    require_bos_window: int | None = None          # BOS within [sweep, sweep + n]
    require_bos_kinds: tuple[str, ...] = ("BOS", "CHOCH")  # spec "BREAK OF STRUCTURE" covers both; recorded per trade
    require_ema13_close: bool = False
    require_htf_zone: bool = False                 # swept zone must come from H4
    require_htf_trend_align: bool = False          # H4 close vs H4 EMA200 + slope
    sl_mode: str = SWEEP_EXTREME
    tp_mode: str = TP_FIXED_RR
    rr: float = PROTOCOL["rr"]


HYPOTHESES: tuple[Hypothesis, ...] = (
    Hypothesis("H1", "Confirmed liquidity sweep alone", ("sweep",)),
    Hypothesis(
        "H2", "Sweep + displacement",
        ("sweep", "displacement"),
        require_displacement_at_least=MODERATE_DISPLACEMENT,
    ),
    Hypothesis(
        "H3", "Sweep + displacement + BOS",
        ("sweep", "displacement", "BOS"),
        require_displacement_at_least=MODERATE_DISPLACEMENT,
        require_bos_window=6,
    ),
    Hypothesis(
        "H4", "Sweep + displacement + BOS + EMA13",
        ("sweep", "displacement", "BOS", "EMA13"),
        require_displacement_at_least=MODERATE_DISPLACEMENT,
        require_bos_window=6,
        require_ema13_close=True,
    ),
    Hypothesis(
        "H5", "Sweep of HTF liquidity + displacement",
        ("sweep:HTF", "displacement"),
        require_displacement_at_least=MODERATE_DISPLACEMENT,
        require_htf_zone=True,
    ),
    Hypothesis(
        "H6", "Sweep + displacement + BOS + MTF alignment",
        ("sweep", "displacement", "BOS", "MTF"),
        require_displacement_at_least=MODERATE_DISPLACEMENT,
        require_bos_window=6,
        require_htf_trend_align=True,
    ),
    Hypothesis(
        "H7", "Sweep + displacement with opposite-liquidity target",
        ("sweep", "displacement", "opposite_liquidity_target"),
        require_displacement_at_least=MODERATE_DISPLACEMENT,
        tp_mode=TP_OPPOSITE_LIQUIDITY,
    ),
    Hypothesis(
        "H8", "Full combination (sweep + displacement + BOS + EMA13 + MTF)",
        ("sweep", "displacement", "BOS", "EMA13", "MTF"),
        require_displacement_at_least=MODERATE_DISPLACEMENT,
        require_bos_window=6,
        require_ema13_close=True,
        require_htf_trend_align=True,
    ),
)


@dataclass(frozen=True)
class Ablation:
    id: str
    title: str
    base: str                 # hypothesis id whose entry set is reused
    variant_field: str        # "sl_mode" | "tp_mode"
    values: tuple[str, ...]


# Report-only comparisons (spec sections 9-10): never auto-adopted.
ABLATIONS: tuple[Ablation, ...] = (
    Ablation("A1", "SL variant ablation on H2 entries", "H2", "sl_mode",
             (SWEEP_EXTREME, ENTRY_SIGNAL_CANDLE, STRUCTURE, ATR_BASED)),
    Ablation("A2", "TP variant ablation on H2 entries", "H2", "tp_mode",
             (TP_FIXED_RR, TP_OPPOSITE_LIQUIDITY, TP_TIME_EXIT)),
)
