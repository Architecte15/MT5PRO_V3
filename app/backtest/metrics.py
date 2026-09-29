from __future__ import annotations

import math
import pandas as pd


def calculate_metrics(trades: pd.DataFrame, starting_equity: float) -> dict[str, float | int]:
    if trades.empty:
        return {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "gross_profit": 0.0,
                "gross_loss": 0.0, "net_profit": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0,
                "max_drawdown_pct": 0.0, "average_trade": 0.0, "average_win": 0.0, "average_loss": 0.0,
                "expectancy": 0.0, "maximum_consecutive_wins": 0, "maximum_consecutive_losses": 0,
                "exposure": 0.0, "risk_per_trade": 0.0, "ending_equity": starting_equity}
    pnl = trades["pnl"].astype(float)
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    equity = starting_equity + pnl.cumsum()
    peak = equity.cummax()
    dd = peak - equity
    dd_pct = dd / peak.replace(0, float("nan")) * 100.0
    seq_w = seq_l = max_w = max_l = 0
    for x in pnl:
        if x > 0: seq_w += 1; seq_l = 0; max_w = max(max_w, seq_w)
        elif x < 0: seq_l += 1; seq_w = 0; max_l = max(max_l, seq_l)
        else: seq_w = seq_l = 0
    gp, gl = float(wins.sum()), float(-losses.sum())
    return {"total_trades": int(len(pnl)), "wins": int((pnl > 0).sum()), "losses": int((pnl < 0).sum()),
            "win_rate": float((pnl > 0).mean()), "gross_profit": gp, "gross_loss": gl,
            "net_profit": float(pnl.sum()), "profit_factor": gp / gl if gl else math.inf,
            "max_drawdown": float(dd.max()), "max_drawdown_pct": float(dd_pct.max()) if not dd_pct.empty else 0.0,
            "average_trade": float(pnl.mean()), "average_win": float(wins.mean()) if not wins.empty else 0.0,
            "average_loss": float(losses.mean()) if not losses.empty else 0.0, "expectancy": float(pnl.mean()),
            "maximum_consecutive_wins": max_w, "maximum_consecutive_losses": max_l,
            "exposure": float(trades["bars_held"].sum()) if "bars_held" in trades else 0.0,
            "risk_per_trade": float(trades["risk_money"].mean()) if "risk_money" in trades else 0.0,
            "ending_equity": float(equity.iloc[-1])}
