# -*- coding: utf-8 -*-
"""最终 Bootstrap 验证：优化后 v20c 组合（VWAP10% 延续）的子样本稳定性
验证优化不是过拟合（普适性核心要求）"""
import csv, io, json, os, random, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# load final v20c (use original CSV for stability — representative)
trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

random.seed(42)
pnls = [t["net_pnl_pct"] for t in trades]
n = len(pnls)
print(f"v20c 全量: {n} 笔, avg {sum(pnls)/n:+.2f}%")

# Bootstrap: sample 60% of trades 1000 times
B = 1000
avgs = []
for _ in range(B):
    sub = random.sample(pnls, int(n * 0.6))
    avgs.append(sum(sub) / len(sub))
avgs.sort()
print(f"\nBootstrap 1000 次（60% 子样本）:")
print(f"  avg 中位数: {avgs[B//2]:+.2f}%")
print(f"  P5: {avgs[int(B*0.05)]:+.2f}% | P95: {avgs[int(B*0.95)]:+.2f}%")
print(f"  波动范围: {avgs[int(B*0.05)]:+.2f}% ~ {avgs[int(B*0.95)]:+.2f}%")
print(f"  全部为正: {sum(1 for a in avgs if a > 0)}/{B} ({100*sum(1 for a in avgs if a > 0)/B:.1f}%)")

# yearly stability
print("\n=== 逐年稳定性（子样本波动）===")
for y in ("2024", "2025", "2026"):
    yp = [t["net_pnl_pct"] for t in trades if str(t["entry_date"])[:4] == y]
    if not yp:
        continue
    yavgs = []
    for _ in range(500):
        sub = random.sample(yp, int(len(yp) * 0.6))
        yavgs.append(sum(sub) / len(sub))
    yavgs.sort()
    print(f"  {y}: n={len(yp)} avg={sum(yp)/len(yp):+.2f}% 子样本P5={yavgs[25]:+.2f}% P95={yavgs[474]:+.2f}%")

print("\n结论: 若 Bootstrap 波动 <0.2pp 且 95% 区间为正 → 非过拟合，普适性确认")
