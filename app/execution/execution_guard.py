from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GuardClaim:
    acquired: bool
    reason: str
    owner: str


class ExecutionGuard:
    """Cross-process guard against duplicate and concurrent entries.

    SQLite gives us an atomic unique claim even when two bot processes start at
    the same time. Stale locks are recoverable after a crash.
    """

    def __init__(self, db_path: str = "runtime/execution_guard.sqlite3", lock_timeout_seconds: float = 10.0):
        self.db_path = Path(db_path)
        self.lock_timeout_seconds = max(float(lock_timeout_seconds), 1.0)
        self.owner = f"{os.getpid()}-{threading.get_ident()}"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS symbol_locks (symbol TEXT PRIMARY KEY, owner TEXT NOT NULL, acquired_at REAL NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS signal_claims (fingerprint TEXT PRIMARY KEY, symbol TEXT NOT NULL, created_at REAL NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS entry_cooldowns (symbol TEXT PRIMARY KEY, available_at REAL NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS daily_entries (day TEXT PRIMARY KEY, count INTEGER NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS filled_entries (symbol TEXT PRIMARY KEY, last_filled_at REAL NOT NULL)")
            conn.commit()

    @staticmethod
    def fingerprint(symbol: str, candle_timestamp: object, direction: str, strategy_id: str) -> str:
        raw = f"{symbol}|{candle_timestamp}|{direction}|{strategy_id}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def claim(self, symbol: str, signal_fingerprint: str, max_trades_per_day: int = 12, min_minutes_between_trades: float = 0.0) -> GuardClaim:
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM symbol_locks WHERE acquired_at < ?", (now - self.lock_timeout_seconds,))
            row = conn.execute("SELECT owner FROM symbol_locks WHERE symbol = ?", (symbol,)).fetchone()
            if row is not None:
                conn.rollback()
                return GuardClaim(False, "execution lock already held for symbol", self.owner)
            cooldown = conn.execute("SELECT available_at FROM entry_cooldowns WHERE symbol = ?", (symbol,)).fetchone()
            if cooldown is not None and float(cooldown[0]) > now:
                remaining = float(cooldown[0]) - now
                conn.rollback()
                return GuardClaim(False, f"entry cooldown active ({remaining:.1f}s remaining)", self.owner)
            day = time.strftime("%Y-%m-%d", time.localtime(now))
            row = conn.execute("SELECT count FROM daily_entries WHERE day = ?", (day,)).fetchone()
            count = int(row[0]) if row else 0
            if count >= int(max_trades_per_day):
                conn.rollback()
                return GuardClaim(False, f"daily trade limit reached ({count}/{max_trades_per_day})", self.owner)
            if min_minutes_between_trades > 0:
                last = conn.execute("SELECT last_filled_at FROM filled_entries WHERE symbol = ?", (symbol,)).fetchone()
                if last and last[0] is not None:
                    elapsed = now - float(last[0])
                    minimum = float(min_minutes_between_trades) * 60.0
                    if elapsed < minimum:
                        conn.rollback()
                        return GuardClaim(False, f"minimum trade interval active ({minimum-elapsed:.1f}s remaining)", self.owner)
            try:
                conn.execute(
                    "INSERT INTO signal_claims(fingerprint, symbol, created_at) VALUES (?, ?, ?)",
                    (signal_fingerprint, symbol, now),
                )
            except sqlite3.IntegrityError:
                conn.rollback()
                return GuardClaim(False, "duplicate signal fingerprint", self.owner)
            conn.execute(
                "INSERT INTO symbol_locks(symbol, owner, acquired_at) VALUES (?, ?, ?)",
                (symbol, self.owner, now),
            )
            conn.commit()
        return GuardClaim(True, "claimed", self.owner)

    def record_filled(self, symbol: str) -> None:
        now = time.time()
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        with self._connect() as conn:
            conn.execute("INSERT INTO filled_entries(symbol, last_filled_at) VALUES (?, ?) ON CONFLICT(symbol) DO UPDATE SET last_filled_at=excluded.last_filled_at", (symbol, now))
            conn.execute("INSERT INTO daily_entries(day, count) VALUES (?, 1) ON CONFLICT(day) DO UPDATE SET count=count+1", (day,))
            conn.commit()

    def daily_count(self) -> int:
        day = time.strftime("%Y-%m-%d", time.localtime())
        with self._connect() as conn:
            row = conn.execute("SELECT count FROM daily_entries WHERE day = ?", (day,)).fetchone()
            return int(row[0]) if row else 0

    def set_cooldown(self, symbol: str, seconds: float) -> None:
        if seconds <= 0:
            return
        with self._connect() as conn:
            available_at = time.time() + float(seconds)
            conn.execute(
                "INSERT INTO entry_cooldowns(symbol, available_at) VALUES (?, ?) "
                "ON CONFLICT(symbol) DO UPDATE SET available_at=excluded.available_at",
                (symbol, available_at),
            )
            conn.commit()

    def release(self, symbol: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM symbol_locks WHERE symbol = ? AND owner = ?", (symbol, self.owner))
            conn.commit()

    def purge_old_claims(self, max_age_seconds: float = 172800.0) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM signal_claims WHERE created_at < ?", (time.time() - max_age_seconds,))
            conn.commit()
