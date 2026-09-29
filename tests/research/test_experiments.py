"""Unit tests: pre-registration integrity of the experiment registry (§17-§18)."""

from dataclasses import asdict

from app.research.displacement import DisplacementParams
from app.research.entries import (
    ATR_BASED,
    ENTRY_SIGNAL_CANDLE,
    STRUCTURE,
    SWEEP_EXTREME,
    TP_FIXED_RR,
    TP_OPPOSITE_LIQUIDITY,
    TP_TIME_EXIT,
)
from app.research.experiments import (
    ABLATIONS,
    DISPLACEMENT_GRID,
    HYPOTHESES,
    PROTOCOL,
)
from app.research import evaluation as ev


def test_hypothesis_ids_unique_and_complete():
    ids = [h.id for h in HYPOTHESES]
    assert ids == [f"H{i}" for i in range(1, 9)]


def test_hypotheses_only_use_declared_modes():
    sl_modes = {ENTRY_SIGNAL_CANDLE, SWEEP_EXTREME, STRUCTURE, ATR_BASED}
    tp_modes = {TP_FIXED_RR, TP_OPPOSITE_LIQUIDITY, TP_TIME_EXIT}
    for h in HYPOTHESES:
        assert h.sl_mode in sl_modes
        assert h.tp_mode in tp_modes
        assert h.components, f"{h.id} must declare its components"
        if h.require_displacement_at_least:
            assert "displacement" in h.components


def test_protocol_split_fractions_sum_to_one():
    s = (PROTOCOL["train_frac"] + PROTOCOL["val_frac"]
         + PROTOCOL["oos_frac"] + PROTOCOL["holdout_frac"])
    assert abs(s - 1.0) < 1e-9
    assert PROTOCOL["min_trades_oos"] >= 30


def test_displacement_grid_contains_defaults():
    defaults = DisplacementParams()
    assert defaults in DISPLACEMENT_GRID
    # grid is strictly ordered by strictness (larger thresholds = pickier)
    strictness = [(g.weak_atr, g.moderate_atr, g.strong_atr) for g in DISPLACEMENT_GRID]
    assert strictness == sorted(strictness)


def test_ablations_reference_real_hypothesis_and_modes():
    hyp_ids = {h.id for h in HYPOTHESES}
    for a in ABLATIONS:
        assert a.base in hyp_ids
        assert a.variant_field in {"sl_mode", "tp_mode"}
        assert len(a.values) >= 2


def test_h7_targets_opposite_liquidity_and_h8_is_full_combo():
    h7 = next(h for h in HYPOTHESES if h.id == "H7")
    h8 = next(h for h in HYPOTHESES if h.id == "H8")
    assert h7.tp_mode == TP_OPPOSITE_LIQUIDITY
    assert {"sweep", "displacement", "opposite_liquidity_target"} <= set(h7.components)
    assert {"sweep", "displacement", "BOS", "EMA13", "MTF"} <= set(h8.components)
    assert h8.require_ema13_close and h8.require_htf_trend_align


def test_prereg_hash_is_stable_across_calls():
    payload = {"protocol": PROTOCOL, "hyp": [asdict(h) for h in HYPOTHESES]}
    assert ev.hash_preregistration(payload) == ev.hash_preregistration(payload)
