"""Per-order filter analysis: classify every baseline order against the new
entry filters (session 07-21, excluded weekdays, excluded hours) and compare
baseline vs filtered backtest results.

Writes backtests/reports/trades_analysis.csv with one row per baseline order.
"""

from __future__ import annotations

from datetime import time

import pandas as pd

from app.config.settings import load_settings
from app.utils.time_utils import in_session, in_trading_window

cfg = load_settings("app/config/default_config.yaml")
sess = cfg.session

base = pd.read_csv("backtests/reports/trades_baseline.csv", parse_dates=["entry_time"])
new = pd.read_csv("backtests/reports/trades.csv", parse_dates=["entry_time"])

df = base.copy()
df["weekday"] = df["entry_time"].dt.weekday  # 0=Monday
df["hour"] = df["entry_time"].dt.hour
df["in_session"] = df["entry_time"].map(
    lambda ts: in_session(ts, sess.start, sess.end, sess.timezone)
)
df["excluded_day"] = df["weekday"].isin(sess.excluded_weekdays)
df["excluded_hour"] = df["hour"].isin(sess.excluded_hours)
df["window_ok"] = df["entry_time"].map(
    lambda ts: in_trading_window(
        ts, sess.start, sess.end, sess.timezone,
        sess.excluded_weekdays, sess.excluded_hours,
    )
)


def dropped_by(row) -> str:
    reasons = []
    if not row["in_session"]:
        reasons.append("session")
    if row["excluded_day"]:
        reasons.append("excluded_day")
    if row["excluded_hour"]:
        reasons.append("excluded_hour")
    return "+".join(reasons) if reasons else ""


df["dropped_by"] = df.apply(dropped_by, axis=1)
df["kept"] = df["window_ok"]

df.to_csv("backtests/reports/trades_analysis.csv", index=False)

kept = df[df["kept"]]
dropped = df[~df["kept"]]

print("=" * 70)
print("PER-ORDER FILTER ANALYSIS (baseline orders vs new entry filters)")
print("=" * 70)
print(f"Baseline orders : {len(df)}")
print(f"Kept            : {len(kept)}  (pnl={kept.pnl.sum():+.5f}, wr={(kept.pnl > 0).mean():.1%})")
print(f"Dropped         : {len(dropped)}  (pnl={dropped.pnl.sum():+.5f}, wr={(dropped.pnl > 0).mean():.1%})")

print("\n-- Marginal effect per filter --")
for label, mask, desc in [
    ("outside session (07-21)", ~df["in_session"], "before day/hour filters"),
    ("excluded weekday (Mon/Tue)", df["excluded_day"], "within session only"),
    ("excluded hours (11-13,16)", df["excluded_hour"], "within session, non-excluded day"),
]:
    if label.startswith("excluded weekday"):
        m = df["in_session"] & mask
    elif label.startswith("excluded hours"):
        m = df["in_session"] & ~df["excluded_day"] & mask
    else:
        m = mask
    sub = df[m]
    print(f"  {label:28s} n={len(sub):3d}  pnl={sub.pnl.sum():+.5f}  wr={(sub.pnl > 0).mean() if len(sub) else 0:.0%}  ({desc})")

print("\n-- Dropped orders by reason --")
print(dropped.groupby("dropped_by").agg(n=("pnl", "size"), pnl=("pnl", "sum")).round(5).to_string())

print("\n-- Kept orders by weekday --")
print(kept.groupby("weekday").agg(n=("pnl", "size"), pnl=("pnl", "sum")).round(5).to_string())

print("\n-- Kept orders by hour --")
print(kept.groupby("hour").agg(n=("pnl", "size"), pnl=("pnl", "sum")).round(5).to_string())

# Cross-check: the filtered backtest should equal the kept baseline set.
new_keys = set(zip(new["entry_time"].astype(str), new["direction"], new["entry"].round(5)))
kept_keys = set(zip(kept["entry_time"].astype(str), kept["direction"], kept["entry"].round(5)))
print("\n-- Verification --")
print(f"Filtered backtest trades : {len(new)}")
print(f"Expected (kept baseline)  : {len(kept_keys)}")
print(f"Exact set match           : {new_keys == kept_keys}")
if new_keys != kept_keys:
    print(f"  only in filtered : {len(new_keys - kept_keys)}")
    print(f"  only in expected : {len(kept_keys - new_keys)}")
