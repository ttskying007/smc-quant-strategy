# -*- coding: utf-8 -*-
"""v20c 连亏分析：最大连亏笔数/连亏分布（实盘心态与风控准备）"""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

trades.sort(key=lambda t: t["entry_date"])
pnls = [t["net_pnl_pct"] for t in trades]

# max consecutive losses
max_streak = 0
cur = 0
streaks = []
for p in pnls:
    if p < 0:
        cur += 1
        max_streak = max(max_streak, cur)
    else:
        if cur > 0:
            streaks.append(cur)
        cur = 0
if cur > 0:
    streaks.append(cur)

print("=== v20c 连亏分析 ===")
print(f"总交易: {len(pnls)}")
print(f"胜率: {100*sum(1 for p in pnls if p>0)/len(pnls):.1f}%")
print(f"最大连亏: {max_streak} 笔")
print(f"连亏分布: {sorted(streaks)[:10]}...")
if streaks:
    print(f"平均连亏: {sum(streaks)/len(streaks):.1f} 笔 | 连亏次数: {len(streaks)}")

# yearly max streaks
by_y = defaultdict(list)
for t in trades:
    by_y[str(t["entry_date"])[:4]].append(t["net_pnl_pct"])
print("\n=== 逐年最大连亏 ===")
for y in ("2024", "2025", "2026"):
    ps = by_y.get(y, [])
    if ps:
        ms = 0
        c = 0
        for p in ps:
            if p < 0:
                c += 1
                ms = max(ms, c)
            else:
                c = 0
        wr = 100 * sum(1 for p in ps if p > 0) / len(ps)
        print(f"  {y}: 最大连亏 {ms} 笔 | WR {wr:.0f}% | n={len(ps)}")
