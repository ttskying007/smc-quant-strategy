# -*- coding: utf-8 -*-
"""信号密度 vs 收益：每月信号数与平均收益的关系（信号密集月是否收益高）"""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

# monthly: count + avg pnl
by_m = defaultdict(list)
for t in trades:
    by_m[str(t["entry_date"])[:6]].append(t["net_pnl_pct"])

months = []
for m, rs in by_m.items():
    if m < "202309":
        continue
    months.append((m, len(rs), sum(rs) / len(rs)))

months.sort(key=lambda x: x[1])  # sort by count
print("=== 信号密度 vs 收益 ===")
print(f"{'月':<8} {'信号数':>6} {'avg%':>8}")
for m, cnt, avg in months:
    print(f"{m:<8} {cnt:>6} {avg:>+7.2f}%")

# density buckets
lo = [a for _, c, a in months if c < 100]
mid = [a for _, c, a in months if 100 <= c < 300]
hi = [a for _, c, a in months if c >= 300]
def avg(x):
    return sum(x) / len(x) if x else 0
print(f"\n低密度(<100/月): n月={len(lo)} avg={avg(lo):+.2f}%")
print(f"中密度(100-300): n月={len(mid)} avg={avg(mid):+.2f}%")
print(f"高密度(300+): n月={len(hi)} avg={avg(hi):+.2f}%")
