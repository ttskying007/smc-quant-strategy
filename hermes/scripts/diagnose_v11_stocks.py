#!/usr/bin/env python3
"""分析高WR vs 低WR股票信号特征差异"""
import json
from pathlib import Path
from collections import Counter

opt_dir = Path('/root/.hermes/smc_opt_v11')
data = json.loads((opt_dir / 'backtest_v11_v3.json').read_text())

stocks = data['stocks']
all_trades = data['all_trades']

# Build per-stock summary
stock_summary = {}
for s in stocks:
    stock_summary[s['symbol']] = s

# Now load optimal params to cross-ref
opt = json.loads((opt_dir / 'optimal_params.json').read_text())

print("=" * 70)
print("HIGH WR vs LOW WR STOCK PROFILE COMPARISON")
print("=" * 70)

# Group stocks by WR
high = [s for s in stocks if s['win_rate'] >= 70 and s['n_trades'] >= 5]
med = [s for s in stocks if 50 <= s['win_rate'] < 70 and s['n_trades'] >= 5]
low = [s for s in stocks if s['win_rate'] < 40 and s['n_trades'] >= 5]

for label, grp in [("WR>=70% (Excellent)", high), ("WR 50-70% (Good)", med), ("WR<40% (Poor)", low)]:
    print(f"\n  {label} ({len(grp)} stocks):")
    print(f"  {'Symbol':<12s} {'WR':>5s} {'RR':>5s} {'PF':>6s} {'Trades':>7s} {'Sigs':>5s} {'SL':>5s} {'TP':>5s} {'Phase':>10s}")
    print(f"  {'-'*12} {'-'*5} {'-'*5} {'-'*6} {'-'*7} {'-'*5} {'-'*5} {'-'*5} {'-'*10}")
    for s in sorted(grp, key=lambda x: x['win_rate'], reverse=True)[:8]:
        sym = s['symbol']
        params = opt.get(sym, {})
        sl = str(params.get('sl_pct','?'))
        tp = str(params.get('tp_pct','?'))
        print(f"  {sym:<12s} {s['win_rate']:>5.1f}% {s['avg_rr']:>4.2f}x {s['profit_factor']:>5.1f} {s['n_trades']:>7d} {s['n_signals']:>5d} {sl:>5s} {tp:>5s} {s.get('phase','?'):>10s}")

print()

# Show what signals look like in high WR vs low WR stocks
print("  SIGNAL COUNT CORRELATION:")
print(f"  High WR avg signals: {sum(s['n_signals'] for s in high)/len(high):.0f}")
print(f"  Low WR avg signals: {sum(s['n_signals'] for s in low)/len(low):.0f}")

# Check phase distribution
from collections import Counter
print(f"\n  Phase distribution:")
for label, grp in [("High WR", high), ("Low WR", low)]:
    phases = Counter(s.get('phase','?') for s in grp)
    print(f"  {label}: {dict(phases)}")

# Check signal density vs WR correlation
print(f"\n  SIGNAL DENSITY (signal count) vs WR:")
import math
buckets = [(0,40, "0-40"), (40,80, "40-80"), (80,120, "80-120"), (120,160, "120-160"), (160, 300, "160+")]
for lo, hi, label in buckets:
    batch = [s for s in stocks if lo <= s['n_signals'] < hi]
    if not batch:
        continue
    avg_wr = sum(s['win_rate'] for s in batch) / len(batch)
    print(f"  {label:>10s} sigs: {len(batch):>3d} stocks, avg WR={avg_wr:.1f}%")

print()

# Per-trade analysis: signal idx distance from end of data
print("  ENTRY POSITION (idx from end) vs WR:")
from collections import defaultdict
pos_data = defaultdict(list)
for t in all_trades:
    pos_data[t['entry_idx']].append(t['won'])

# Group by proximity to end
for max_idx, label in [(250, "Recent (idx>=250)"), (200, "idx>=200"), (150, "idx>=150"), (100, "idx>=100"), (50, "idx>=50"), (0, "All")]:
    trades = [t for t in all_trades if t['entry_idx'] >= max_idx]
    if not trades:
        continue
    wr = sum(1 for t in trades if t['won']) / len(trades) * 100
    pct = len(trades) / len(all_trades) * 100
    print(f"  {label:<20s}: {len(trades):>4d} trades ({pct:.0f}%), WR={wr:.1f}%")

print()
print("=" * 70)
