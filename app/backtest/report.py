from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def make_equity_curve(trades, starting_equity: float, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if trades.empty:
        fig, ax = plt.subplots()
        ax.set_title("No trades")
        fig.savefig(path)
        plt.close(fig)
        return
    eq = starting_equity + trades["pnl"].cumsum()
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(eq.index, eq.values)
    ax.set_title("Equity curve")
    ax.set_xlabel("Trade")
    ax.set_ylabel("Equity")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def make_funnel_chart(funnel: dict[str, int], path: str | Path) -> None:
    """Export a simple diagnostic chart of the setup funnel."""
    keys = [
        "candles_analyzed", "htf_context_valid", "structural_setups", "breakouts",
        "retests", "price_action_confirmations", "indicator_confirmations",
        "score_candidates", "risk_accepted", "executed_trades",
    ]
    values = [funnel.get(k, 0) for k in keys]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(range(len(keys)), values)
    ax.set_xticks(range(len(keys)), [k.replace("_", " ") for k in keys], rotation=45, ha="right")
    ax.set_ylabel("Count")
    ax.set_title("Backtest setup funnel")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
