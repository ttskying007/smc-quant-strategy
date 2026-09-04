#!/usr/bin/env python3
"""诊断v7.1回测结果 — 输单模式和序列WR"""
import json
from collections import Counter

data = json.load(open('/root/.hermes/smc_opt_v11/backtest_v11_v7.json'))
trades = data['all_trades']
stocks = data['stocks']

n = len(trades)
wins = sum(1 for t in trades if t['won'])

print(f"Total: {n} trades, {wins} wins, WR={wins/n*100:.1f}%")
print()

# === WR by Sequence Type ===
seq_wr, seq_total = Counter(), Counter()
for t in trades:
    seq = t.get('seq_name','?')
    seq_total[seq] += 1
    if t['won']: seq_wr[seq] += 1

print("=== WR by Sequence Type ===")
for s, cnt in seq_total.most_common():
    wr = seq_wr[s]/cnt*100
    print(f"  {s:20s}: {cnt:4d} trades, WR={wr:.1f}%")

# === Losing Trade Diagnostics ===
print()
losers = [t for t in trades if not t['won']]
print(f"=== Losing Trade Diagnostics (N={len(losers)}) ===")
hold_cnt = Counter(t['hold_bars'] for t in losers)
print(f"  Hold bars dist: {dict(hold_cnt.most_common(10))}")
losses = sorted([t['pnl_pct'] for t in losers])
print(f"  Loss range: {losses[0]:.2f}% to {losses[-1]:.2f}%")
print(f"  Avg loss: {sum(losses)/len(losses):.2f}%")

# === Winning Trade Diagnostics ===
print()
winners = [t for t in trades if t['won']]
print(f"=== Winning Trade Diagnostics (N={len(winners)}) ===")
hold_w = Counter(t['hold_bars'] for t in winners)
print(f"  Hold bars dist: {dict(hold_w.most_common(10))}")
gains = sorted([t['pnl_pct'] for t in winners])
print(f"  Gain range: {gains[0]:.2f}% to {gains[-1]:.2f}%")
print(f"  Avg gain: {sum(gains)/len(gains):.2f}%")
full_tp = sum(1 for t in winners if t['pnl_pct']>=5)
print(f"  WR>=5% (full TP): {full_tp}/{len(winners)} = {full_tp/len(winners)*100:.1f}%")
partial = sum(1 for t in winners if 0<t['pnl_pct']<5)
print(f"  Partial win (0-5%): {partial}/{len(winners)} = {partial/len(winners)*100:.1f}%")

# === Resonance Grade Distribution ===
print()
grades = Counter(t.get('resonance_grade','?') for t in trades)
print("=== Resonance Grade Distribution ===")
for g, cnt in grades.most_common():
    w = sum(1 for t in trades if t.get('resonance_grade','')==g and t['won'])
    print(f"  Grade {g:5s}: {cnt:4d} trades, WR={w/cnt*100:.1f}%")

# === Trade count vs WR relationship ===
print()
print("=== Trade Count vs WR ===")
buckets = [(0,5),(5,10),(10,20),(20,999)]
for lo, hi in buckets:
    subset = [s for s in stocks if lo <= s['n_trades'] < hi]
    if subset:
        avg_wr = sum(s['win_rate'] for s in subset)/len(subset)
        print(f"  Trades [{lo}-{hi}): {len(subset):2d} stocks, avg WR={avg_wr:.1f}%")

# === Signal density ===
print()
print("=== Signal Density vs WR ===")
buckets2 = [(0,50),(50,80),(80,110),(110,150),(150,999)]
for lo, hi in buckets2:
    subset = [s for s in stocks if lo <= s.get('n_signals',0) < hi]
    if subset:
        avg_wr = sum(s['win_rate'] for s in subset)/len(subset)
        print(f"  Signals [{lo}-{hi}): {len(subset):2d} stocks, avg WR={avg_wr:.1f}%")

# === High/Low WR stock comparison ===
print()
high_wr = [s for s in stocks if s['win_rate']>=70]
low_wr = [s for s in stocks if s['win_rate']<40]
print(f"=== High WR (>=70%, N={len(high_wr)}) vs Low WR (<40%, N={len(low_wr)}) ===")
print(f"  High WR: avg trades={sum(s['n_trades'] for s in high_wr)/len(high_wr):.0f}")
print(f"  Low WR:  avg trades={sum(s['n_trades'] for s in low_wr)/len(low_wr):.0f}")
ph_h = Counter(s['phase'] for s in high_wr)
ph_l = Counter(s['phase'] for s in low_wr)
print(f"  High WR phases: {dict(ph_h.most_common())}")
print(f"  Low WR phases:  {dict(ph_l.most_common())}")

# === Confidence breakdown ===
print()
print("=== Entry Confidence vs WR ===")
confs = Counter(t.get('confidence',0)//0.1*0.1 for t in trades)
for c in sorted(confs.keys()):
    subset = [t for t in trades if t.get('confidence',0)//0.1*0.1 == c]
    w = sum(1 for t in subset if t['won'])
    print(f"  Confidence {c:.1f}: {len(subset):4d} trades, WR={w/len(subset)*100:.1f}%")
