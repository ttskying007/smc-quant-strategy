# -*- coding: utf-8 -*-
"""v20c 月度表现更新（8-20 数据）—— 最新月度确认 + 弱月日历验证"""
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

by_m = defaultdict(list)
for t in trades:
    m = str(t["entry_date"])[:6]
    if m >= "202309":
        by_m[m].append(t["net_pnl_pct"])

months = sorted(by_m.keys())
print(f"总月份: {len(months)} | 正月份: {sum(1 for m in months if sum(by_m[m])/len(by_m[m])>0)}")
print("\n=== 2026 月度 ===")
for m in [x for x in months if x.startswith("2026")]:
    rs = by_m[m]
    wins = sum(1 for x in rs if x > 0)
    print(f"  {m}: n={len(rs)} avg={sum(rs)/len(rs):+.2f}% WR={100*wins/len(rs):.0f}%")
print("\n=== 弱月日历验证（2023-09~2026-08）===")
# 8月 (当前月)
aug = [sum(by_m[m])/len(by_m[m]) for m in months if m.endswith("08")]
if aug:
    print(f"  8月: {aug}")
