#!/usr/bin/env python3
"""Analyze V11 baseline results"""
import json, sys
from pathlib import Path
from collections import Counter

data = json.loads(Path('/root/.hermes/smc_opt_v11/v11_1_baseline.json').read_text())

print("=" * 70)
print("V11.1 基线回测分析")
print("=" * 70)

# Per-sequence breakdown
sequences = data.get('sequences', {})
print(f"\n序列分布:")
total_trades = sum(sequences.values())
for name, cnt in sorted(sequences.items(), key=lambda x: -x[1]):
    pct = cnt / total_trades * 100
    print(f"  {name:25s}: {cnt:4d} ({pct:.0f}%)")

# Stock-level analysis
per_stock = data.get('per_stock', {})
stocks_with_trades = {k: v for k, v in per_stock.items() if v.get('n_trades', 0) >= 3}

wr_buckets = Counter()
for s, stats in stocks_with_trades.items():
    wr = stats.get('win_rate', 0)
    if wr >= 80: wr_buckets['80-100%'] += 1
    elif wr >= 60: wr_buckets['60-80%'] += 1
    elif wr >= 40: wr_buckets['40-60%'] += 1
    elif wr >= 20: wr_buckets['20-40%'] += 1
    else: wr_buckets['0-20%'] += 1

print(f"\n胜率分布 ({len(stocks_with_trades)} 只有交易的股票):")
for bucket, cnt in sorted(wr_buckets.items()):
    print(f"  WR {bucket:10s}: {cnt:3d}只")

# Best and worst
sorted_by_wr = sorted(stocks_with_trades.items(), key=lambda x: -x[1].get('win_rate', 0))
print(f"\n最佳5只 (高WR):")
for s, st in sorted_by_wr[:5]:
    print(f"  {s:12s}: WR={st['win_rate']:5.1f}% N={st['n_trades']:2d} RR={st['avg_rr']:.2f}x PF={st['profit_factor']:.2f}")

print(f"\n最差5只 (低WR):")
for s, st in sorted_by_wr[-5:]:
    print(f"  {s:12s}: WR={st['win_rate']:5.1f}% N={st['n_trades']:2d} RR={st['avg_rr']:.2f}x PF={st['profit_factor']:.2f}")

# High trade count stocks
print(f"\n高交易量股票 (N>=20):")
for s, st in sorted([x for x in stocks_with_trades.items() if x[1].get('n_trades',0) >= 20], key=lambda x: -x[1]['n_trades'])[:10]:
    print(f"  {s:12s}: N={st['n_trades']:2d} WR={st['win_rate']:5.1f}% RR={st['avg_rr']:.2f}x PF={st['profit_factor']:.2f}")

# RR distribution
rr_buckets = Counter()
for s, st in stocks_with_trades.items():
    rr = st.get('avg_rr', 1)
    if rr >= 3: rr_buckets['3x+'] += 1
    elif rr >= 2: rr_buckets['2-3x'] += 1
    elif rr >= 1.5: rr_buckets['1.5-2x'] += 1
    else: rr_buckets['<1.5x'] += 1

print(f"\n盈亏比分布 ({len(stocks_with_trades)} 只):")
for bucket, cnt in sorted(rr_buckets.items()):
    print(f"  RR {bucket:10s}: {cnt:3d}只")
