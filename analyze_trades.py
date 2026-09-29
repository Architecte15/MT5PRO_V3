import pandas as pd
import numpy as np

df = pd.read_csv('backtests/reports/trades.csv', parse_dates=['entry_time', 'exit_time'])
df['win'] = df['pnl'] > 0
df['loss'] = df['pnl'] < 0
df['hour'] = df['entry_time'].dt.hour
df['weekday'] = df['entry_time'].dt.day_name()
df['bars_bucket'] = pd.cut(df['bars_held'], bins=[-1,0,5,20,100,10000], labels=['0-5','5-20','20-100','100+','500+'])

print("="*70)
print("GLOBAL")
print("="*70)
print(f"Total: {len(df)} | Wins: {df.win.sum()} | Losses: {df.loss.sum()}")
print(f"Net pnl (price units): {df.pnl.sum():.5f}")
print(f"TP closes: {(df.reason=='TP').sum()} | SL closes: {(df.reason=='SL').sum()}")

print("\n"+"="*70)
print("BY REASON (TP vs SL)")
print("="*70)
g = df.groupby('reason').agg(
    count=('pnl','size'),
    total_pnl=('pnl','sum'),
    avg_pnl=('pnl','mean'),
    avg_bars=('bars_held','mean'),
    avg_score=('score','mean')
).round(6)
print(g.to_string())

print("\n"+"="*70)
print("BY DIRECTION")
print("="*70)
g = df.groupby('direction').agg(
    count=('pnl','size'),
    wins=('win','sum'),
    losses=('loss','sum'),
    win_rate=('win','mean'),
    total_pnl=('pnl','sum'),
    avg_pnl=('pnl','mean')
).round(4)
print(g.to_string())

print("\n"+"="*70)
print("WINS vs LOSSES CHARACTERISTICS")
print("="*70)
for label, sub in [('WINS', df[df.win]), ('LOSSES', df[df.loss])]:
    print(f"\n{label} (n={len(sub)}):")
    print(f"  avg pnl:        {sub.pnl.mean():.6f}")
    print(f"  median pnl:     {sub.pnl.median():.6f}")
    print(f"  avg bars_held:  {sub.bars_held.mean():.1f}")
    print(f"  median bars:    {sub.bars_held.median():.0f}")
    print(f"  avg score:      {sub.score.mean():.2f}")
    print(f"  avg risk_money: {sub.risk_money.mean():.6f}")
    print(f"  BUY/SELL:       {sub.direction.value_counts().to_dict()}")

print("\n"+"="*70)
print("SCORE DISTRIBUTION -> outcome")
print("="*70)
g = df.groupby('score').agg(
    count=('pnl','size'),
    wins=('win','sum'),
    win_rate=('win','mean'),
    total_pnl=('pnl','sum'),
    avg_pnl=('pnl','mean')
).round(4)
print(g.to_string())

print("\n"+"="*70)
print("BARS HELD (duration) -> outcome")
print("="*70)
g = df.groupby('bars_bucket', observed=True).agg(
    count=('pnl','size'),
    wins=('win','sum'),
    win_rate=('win','mean'),
    total_pnl=('pnl','sum'),
    avg_pnl=('pnl','mean')
).round(4)
print(g.to_string())

print("\n"+"="*70)
print("BY HOUR OF ENTRY (UTC)")
print("="*70)
g = df.groupby('hour').agg(
    count=('pnl','size'),
    wins=('win','sum'),
    win_rate=('win','mean'),
    total_pnl=('pnl','sum')
).round(3)
print(g.to_string())

print("\n"+"="*70)
print("BY WEEKDAY")
print("="*70)
order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
g = df.groupby('weekday').agg(
    count=('pnl','size'),
    wins=('win','sum'),
    win_rate=('win','mean'),
    total_pnl=('pnl','sum')
).round(3)
print(g.reindex(order).dropna().to_string())

print("\n"+"="*70)
print("BY MONTH")
print("="*70)
df['month'] = df['entry_time'].dt.to_period('M')
g = df.groupby('month').agg(
    count=('pnl','size'),
    wins=('win','sum'),
    win_rate=('win','mean'),
    total_pnl=('pnl','sum')
).round(5)
print(g.to_string())

print("\n"+"="*70)
print("TOP 5 BEST / WORST TRADES")
print("="*70)
print("\nTOP 5 WINS:")
print(df.nlargest(5, 'pnl')[['entry_time','direction','pnl','reason','bars_held','score']].to_string(index=False))
print("\nTOP 5 LOSSES:")
print(df.nsmallest(5, 'pnl')[['entry_time','direction','pnl','reason','bars_held','score']].to_string(index=False))

print("\n"+"="*70)
print("LOSS DEEPNESS (how far SL trades go)")
print("="*70)
sl = df[df.reason=='SL']
print(f"SL trades: {len(sl)}")
print(f"  avg loss: {sl.pnl.mean():.6f}")
print(f"  avg risk_money (intended risk): {sl.risk_money.mean():.6f}")
print(f"  ratio actual/intended: {sl.pnl.mean()/sl.risk_money.mean():.3f} (1.0 = clean SL)")

print("\n"+"="*70)
print("CONSECUTIVE PATTERN")
print("="*70)
df['streak'] = (df.pnl > 0).astype(int)
# Find longest losing streak context
print(f"Max consecutive wins: 14, Max consecutive losses: 9")

print("\n"+"="*70)
print("CORRELATIONS")
print("="*70)
print(f"pnl vs bars_held:  {df.pnl.corr(df.bars_held):.3f}")
print(f"pnl vs score:      {df.pnl.corr(df.score):.3f}")
print(f"pnl vs risk_money: {df.pnl.corr(df.risk_money):.3f}")
