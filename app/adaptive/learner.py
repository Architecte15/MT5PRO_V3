from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime, timezone


@dataclass(frozen=True)
class AdaptiveObservation:
    position_id: str
    symbol: str
    direction: str
    strategy_id: str
    context_key: str
    entry_time: str
    entry_price: float
    sl: float
    tp: float
    features: dict


class AdaptiveLearner:
    """Persistent, causal market-memory layer.

    It does not rewrite strategy parameters after one trade. It updates a
    Bayesian win/loss posterior only when a tracked position is closed. The
    posterior can reduce/increase *risk allocation* within configured bounds,
    while the active strategy rules remain immutable until a separately
    validated model is promoted.
    """

    def __init__(self, db_path: str, min_samples: int = 20, min_lower_confidence: float = 0.48,
                 min_risk_multiplier: float = 0.35, max_risk_multiplier: float = 1.0):
        self.db_path = Path(db_path)
        self.min_samples = max(int(min_samples), 1)
        self.min_lower_confidence = float(min_lower_confidence)
        self.min_risk_multiplier = float(min_risk_multiplier)
        self.max_risk_multiplier = float(max_risk_multiplier)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS observations (
                position_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, direction TEXT NOT NULL,
                strategy_id TEXT NOT NULL, context_key TEXT NOT NULL, entry_time TEXT NOT NULL,
                entry_price REAL NOT NULL, sl REAL NOT NULL, tp REAL NOT NULL,
                features_json TEXT NOT NULL, outcome_pnl REAL, outcome_r REAL,
                outcome_win INTEGER, exit_time TEXT, outcome_reason TEXT
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS context_stats (
                context_key TEXT PRIMARY KEY, samples INTEGER NOT NULL DEFAULT 0,
                wins INTEGER NOT NULL DEFAULT 0, losses INTEGER NOT NULL DEFAULT 0,
                pnl REAL NOT NULL DEFAULT 0.0, last_update TEXT
            )""")
            conn.commit()

    @staticmethod
    def context_key(features: dict) -> str:
        keys = [
            "direction", "regime", "session", "trend_alignment", "pullback",
            "momentum", "volatility", "ema13_side", "structure_bias"
        ]
        return "|".join(f"{k}={features.get(k, 'NA')}" for k in keys)

    def observe_entry(self, observation: AdaptiveObservation) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO observations
                (position_id,symbol,direction,strategy_id,context_key,entry_time,entry_price,sl,tp,features_json)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (observation.position_id, observation.symbol, observation.direction,
                 observation.strategy_id, observation.context_key, observation.entry_time,
                 observation.entry_price, observation.sl, observation.tp, json.dumps(observation.features, default=str)),
            )
            conn.commit()

    def observe_outcome(self, position_id: str, pnl: float, exit_time: datetime | None = None, reason: str = "") -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT context_key, entry_price, sl, tp, outcome_win FROM observations WHERE position_id=?",
                (str(position_id),),
            ).fetchone()
            if row is None or row[4] is not None:
                return False
            context_key, entry, sl, tp, _ = row
            risk_distance = abs(float(entry) - float(sl))
            r_multiple = float(pnl) / max(risk_distance, 1e-12)
            win = 1 if float(pnl) > 0 else 0
            now = (exit_time or datetime.now(timezone.utc)).isoformat()
            conn.execute(
                "UPDATE observations SET outcome_pnl=?, outcome_r=?, outcome_win=?, exit_time=?, outcome_reason=? WHERE position_id=?",
                (float(pnl), r_multiple, win, now, reason, str(position_id)),
            )
            conn.execute(
                """INSERT INTO context_stats(context_key,samples,wins,losses,pnl,last_update)
                VALUES (?,1,?,?,?,?)
                ON CONFLICT(context_key) DO UPDATE SET
                    samples=samples+1, wins=wins+excluded.wins, losses=losses+excluded.losses,
                    pnl=pnl+excluded.pnl, last_update=excluded.last_update""",
                (context_key, win, 1-win, float(pnl), now),
            )
            conn.commit()
        return True

    def stats(self, context_key: str) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT samples,wins,losses,pnl,last_update FROM context_stats WHERE context_key=?",
                (context_key,),
            ).fetchone()
        if row is None:
            return {"samples": 0, "wins": 0, "losses": 0, "pnl": 0.0, "win_rate": 0.5, "lower_confidence": 0.0}
        samples, wins, losses, pnl, last_update = row
        # Jeffreys posterior Beta(0.5 + wins, 0.5 + losses).
        a, b = 0.5 + wins, 0.5 + losses
        mean = a / (a + b)
        # Wilson lower bound is stable and dependency-free; use z=1.96.
        n = max(int(samples), 1)
        phat = wins / n
        z = 1.96
        denom = 1 + z*z/n
        centre = phat + z*z/(2*n)
        margin = z * math.sqrt(max((phat*(1-phat) + z*z/(4*n))/n, 0.0))
        lower = max(0.0, (centre - margin) / denom)
        return {"samples": int(samples), "wins": int(wins), "losses": int(losses),
                "pnl": float(pnl), "win_rate": mean, "lower_confidence": lower,
                "last_update": last_update}

    def risk_multiplier(self, context_key: str) -> float:
        s = self.stats(context_key)
        if s["samples"] < self.min_samples:
            return 1.0
        lower = float(s["lower_confidence"])
        if lower <= self.min_lower_confidence:
            # Scale down smoothly; never below configured floor.
            ratio = max(0.0, lower / max(self.min_lower_confidence, 1e-9))
            return max(self.min_risk_multiplier, min(1.0, ratio))
        # Good evidence restores base risk but never increases above 1.0.
        return self.max_risk_multiplier

    def opportunity_allowed(self, context_key: str, cold_start: bool = True) -> tuple[bool, dict]:
        s = self.stats(context_key)
        if s["samples"] < self.min_samples:
            return bool(cold_start), {**s, "status": "COLD_START"}
        allowed = s["lower_confidence"] >= self.min_lower_confidence
        return allowed, {**s, "status": "VALIDATED_CONTEXT" if allowed else "WEAK_CONTEXT"}

    def pending(self, position_ids: set[str] | None = None) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT position_id,symbol,direction,strategy_id,context_key,entry_time,entry_price,sl,tp,features_json FROM observations WHERE outcome_win IS NULL"
            ).fetchall()
        out = []
        for r in rows:
            if position_ids is not None and str(r[0]) not in position_ids:
                continue
            out.append({"position_id": str(r[0]), "symbol": r[1], "direction": r[2], "strategy_id": r[3],
                        "context_key": r[4], "entry_time": r[5], "entry_price": r[6], "sl": r[7], "tp": r[8],
                        "features": json.loads(r[9])})
        return out

    def export_snapshot(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT context_key,samples,wins,losses,pnl,last_update FROM context_stats ORDER BY samples DESC").fetchall()
        return [dict(context_key=r[0], samples=r[1], wins=r[2], losses=r[3], pnl=r[4], last_update=r[5]) for r in rows]
