#!/usr/bin/env python3
"""V470 信号密度诊断 + 三套收紧方案AB对比"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')

# === 基准数据 ===
data = json.load(open('/root/.hermes/smc_opt_v470/v470_full_stocks.json'))
trades = json.load(open('/root/.hermes/smc_opt_v470/v470_full_trades.json'))

# 按RR分档统计
print("=== 当前RR分布 ===")
brackets = [(0,2), (2,4), (4,6), (6,8), (8,10), (10,20), (20,100)]
for lo, hi in brackets:
    cnt = sum(1 for t in trades if lo <= t['rr'] < hi)
    if cnt: print(f"  RR {lo:4.1f}-{hi:4.1f}x: {cnt:3d}笔 ({cnt/len(trades)*100:.1f}%)")

# OB强度分布
obs = [t for t in trades if 'OB' in t.get('entry_type','')]
strengths = [t.get('strength', 0) for t in obs]
print(f"\n=== OB信号强度分布 ===")
print(f"  总OB: {len(obs)}笔")
print(f"  strength范围: {min(strengths):.2f} - {max(strengths):.2f}")
print(f"  平均strength: {sum(strengths)/len(strengths):.2f}")
for th in [0.5, 1.0, 1.5, 2.0, 3.0]:
    above = sum(1 for s in strengths if s >= th)
    print(f"  strength >= {th:.1f}: {above}笔 ({above/len(obs)*100:.0f}%)")

# displacement分布
disps = [t.get('displacement_ratio', 0) for t in obs if t.get('displacement_ratio', 0) > 0]
print(f"\n=== OB位移比分布 ===")
print(f"  有displacement的OB: {len(disps)}笔")
if disps:
    print(f"  范围: {min(disps):.2f} - {max(disps):.2f}")
    print(f"  平均: {sum(disps)/len(disps):.2f}")
    for th in [0.5, 1.0, 1.5, 2.0, 3.0]:
        above = sum(1 for d in disps if d >= th)
        print(f"  displacement >= {th:.1f}: {above}笔 ({above/len(disps)*100:.0f}%)")

# 每只股票交易数分布
from collections import Counter
stock_cnt = Counter(t['symbol'] for t in trades)
cnt_dist = Counter(stock_cnt.values())
print(f"\n=== 每只股票交易数分布 ===")
for n in sorted(cnt_dist.keys()):
    print(f"  {n}笔: {cnt_dist[n]}只股票")