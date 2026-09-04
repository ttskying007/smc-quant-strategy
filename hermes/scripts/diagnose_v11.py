#!/usr/bin/env python3
"""深诊断 V11.2 — 分析WR分布根因"""
import json
from pathlib import Path
from collections import Counter, defaultdict

opt_dir = Path('/root/.hermes/smc_opt_v11')
data = json.loads((opt_dir / 'backtest_v11_v3.json').read_text())

all_trades = data['all_trades']
stocks = data['stocks']

print("=" * 70)
print("V11.2 DEEP DIAGNOSIS")
print("=" * 70)

# 1. WR per sequence type
seq_wr = defaultdict(list)
for t in all_trades:
    seq = t.get('seq_name', 'UNKNOWN')
    seq_wr[seq].append(t)

print("\n  WR BY SEQUENCE TYPE:")
header = f"  {'Sequence':<25s} {'Trades':>7s} {'Wins':>5s} {'WR':>6s} {'AvgRR':>7s} {'AvgPnl':>8s} {'%ofTotal':>9s}"
print(header)
print(f"  {'-'*25} {'-'*7} {'-'*5} {'-'*6} {'-'*7} {'-'*8} {'-'*9}")

seq_by_pct = sorted(seq_wr.items(), key=lambda x: len(x[1]), reverse=True)
for seq, trades in seq_by_pct:
    n = len(trades)
    wins = sum(1 for t in trades if t['won'])
    wr = wins / n * 100
    rr_vals = [t['rr'] for t in trades]
    avg_rr = sum(rr_vals) / len(rr_vals)
    avg_pnl = sum(t['pnl_pct'] for t in trades) / n
    pct = n / len(all_trades) * 100
    print(f"  {seq:<25s} {n:>7d} {wins:>5d} {wr:>5.1f}% {avg_rr:>6.2f}x {avg_pnl:>+7.2f}% {pct:>7.1f}%")

print()

# 2. WR by resonance grade
grade_wr = defaultdict(list)
for t in all_trades:
    grade = t.get('resonance_grade', '?')
    grade_wr[grade].append(t)

print("  WR BY RESONANCE GRADE:")
for g in ['S','A','B','C','D']:
    trades = grade_wr.get(g, [])
    if not trades:
        continue
    n = len(trades)
    wins = sum(1 for t in trades if t['won'])
    wr = wins / n * 100
    print(f"  Grade {g}: {n:>4d} trades, WR={wr:>5.1f}%")

print()

# 3. Scout vs Silver/Gold Analysis
print("  SEQUENCE TIER ANALYSIS:")
for label, condition in [
    ("SCOUT (single sig)", lambda t: 'SCOUT' in t.get('seq_name','')),
    ("BRONZE (2 sig)", lambda t: 'BRONZE' in t.get('seq_name','')),
    ("SILVER (3 sig)", lambda t: 'SILVER' in t.get('seq_name','')),
]:
    trades = [t for t in all_trades if condition(t)]
    if not trades:
        continue
    n = len(trades)
    wins = sum(1 for t in trades if t['won'])
    wr = wins / n * 100
    confs = [t['confidence'] for t in trades]
    avg_conf = sum(confs) / len(confs)
    rr_vals = [t['rr'] for t in trades]
    avg_rr = sum(rr_vals) / len(rr_vals)
    hold = [t['hold_bars'] for t in trades]
    avg_hold = sum(hold) / len(hold)
    print(f"  {label:<25s}: n={n:>4d} WR={wr:>5.1f}% avgConf={avg_conf:.3f} avgRR={avg_rr:.2f}x avgHold={avg_hold:.1f}")

print()

# 4. Stock quality analysis
print("  STOCK QUALITY BREAKDOWN:")
high_wr = [s for s in stocks if s['win_rate'] >= 60 and s['n_trades'] >= 5]
mid_wr = [s for s in stocks if 40 <= s['win_rate'] < 60 and s['n_trades'] >= 5]
low_wr = [s for s in stocks if s['win_rate'] < 40 and s['n_trades'] >= 5]

for label, grp in [("HIGH (WR>=60%)", high_wr), ("MID (40-60%)", mid_wr), ("LOW (WR<40%)", low_wr)]:
    if not grp:
        continue
    n_stocks = len(grp)
    avg_wr = sum(s['win_rate'] for s in grp) / n_stocks
    avg_rr = sum(s['avg_rr'] for s in grp) / n_stocks
    avg_pf = sum(s['profit_factor'] for s in grp) / n_stocks
    avg_trades = sum(s['n_trades'] for s in grp) / n_stocks
    avg_pnl = sum(s['avg_pnl'] for s in grp) / n_stocks
    avg_sigs = sum(s['n_signals'] for s in grp) / n_stocks
    print(f"  {label:<20s}: n={n_stocks:>3d} WR={avg_wr:>5.1f}% RR={avg_rr:>4.2f}x PF={avg_pf:>6.2f} trades/stk={avg_trades:.1f} PnL={avg_pnl:>+5.2f}% sigs={avg_sigs:.0f}")

print()

# 5. Hold bars distribution
print("  HOLD BARS vs WR:")
hold_data = defaultdict(list)
for t in all_trades:
    hold_data[t['hold_bars']].append(t)
for hb in sorted(hold_data):
    trades = hold_data[hb]
    wr = sum(1 for t in trades if t['won']) / len(trades) * 100
    n = len(trades)
    bars_vis = '#' * min(40, n // 5)
    print(f"  {hb:>2d} bars: {n:>4d} trades, WR={wr:>5.1f}% {bars_vis}")

print()

# 6. Direction
print("  DIRECTION ASYMMETRY:")
for direction in ['bull', 'bear']:
    trades = [t for t in all_trades if t['direction'] == direction]
    if not trades:
        continue
    n = len(trades)
    wins = sum(1 for t in trades if t['won'])
    wr = wins / n * 100
    rr = sum(t['rr'] for t in trades) / n
    pnl = sum(t['pnl_pct'] for t in trades) / n
    print(f"  {direction:<10s}: {n:>4d} trades, WR={wr:>5.1f}% avgRR={rr:.2f}x avgPnl={pnl:+.2f}%")

print()

# 7. Confidence threshold analysis
print("  CONFIDENCE THRESHOLD OPTIMIZATION:")
buckets = [(0.45, 0.50), (0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 0.80), (0.80, 1.0)]
for lo, hi in buckets:
    trades = [t for t in all_trades if lo <= t['confidence'] < hi]
    if not trades:
        continue
    n = len(trades)
    wins = sum(1 for t in trades if t['won'])
    wr = wins / n * 100
    rr = sum(t['rr'] for t in trades) / n
    avg_conf = sum(t['confidence'] for t in trades) / n
    pct = n / len(all_trades) * 100
    print(f"  [{lo:.2f},{hi:.2f}): {n:>4d} trades ({pct:>4.1f}%), WR={wr:>5.1f}% RR={rr:.2f}x avgConf={avg_conf:.3f}")

print()

# 8. Signal type distribution of Scout trades
print("  SCOUT TRADE SIGNAL TYPES:")
scout_trades = [t for t in all_trades if 'SCOUT' in t.get('seq_name','')]
sig_types = defaultdict(list)
for t in scout_trades:
    seq = t.get('seq_name', '?')
    sig_types[seq].append(t)
for sig in sorted(sig_types, key=lambda s: len(sig_types[s]), reverse=True):
    trades = sig_types[sig]
    wr = sum(1 for t in trades if t['won']) / len(trades) * 100
    print(f"  {sig:<25s}: {len(trades):>4d} trades, WR={wr:>5.1f}%")

print()

# 9. Stock-level: what makes WR break?
print("  TOP 10 HIGH WR STOCKS:")
for s in sorted(high_wr, key=lambda x: x['win_rate'], reverse=True)[:10]:
    print(f"  {s['symbol']:<12s} WR={s['win_rate']:>5.1f}% RR={s['avg_rr']:.2f}x PF={s['profit_factor']:.1f} trades={s['n_trades']} sigs={s['n_signals']}")

print("  BOTTOM 10 LOW WR STOCKS:")
for s in sorted(low_wr, key=lambda x: x['win_rate'])[:10]:
    print(f"  {s['symbol']:<12s} WR={s['win_rate']:>5.1f}% RR={s['avg_rr']:.2f}x PF={s['profit_factor']:.1f} trades={s['n_trades']} sigs={s['n_signals']}")

print()
print("=" * 70)
