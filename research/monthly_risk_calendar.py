# -*- coding: utf-8 -*-
"""Event-leg monthly risk calendar: which months are systematically weak for event stocks?
8-19 fall (-4.9%) - is August a seasonal weak month (2024-08 was -1.70%)?"""
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_v18_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        if r.get("src") == "EVENT":
            r["net_pnl_pct"] = float(r["net_pnl_pct"])
            trades.append(r)

# monthly avg for event trades across all years
by_m = defaultdict(list)
for t in trades:
    by_m[str(t["entry_date"])[4:6]].append(t["net_pnl_pct"])

print("=== 事件腿月度风险日历（所有年份合并，15/20日持有）===")
print(f"{'月':<4} {'n':>6} {'avg%':>8} {'WR%':>6} {'弱月?'}")
for m in sorted(by_m):
    rs = by_m[m]
    avg = sum(rs) / len(rs)
    w = sum(1 for x in rs if x > 0) / len(rs) * 100
    flag = " <<<" if avg < -0.5 else ""
    print(f"{m:<4} {len(rs):>6} {avg:>+7.2f}% {w:>5.0f}%{flag}")

# August detail by year
print("\n=== 8 月逐年 ===")
by_ym = defaultdict(list)
for t in trades:
    by_ym[str(t["entry_date"])[:6]].append(t["net_pnl_pct"])
for ym in sorted(by_ym):
    if ym[4:6] == "08":
        rs = by_ym[ym]
        print(f"  {ym}: n={len(rs)} avg={sum(rs)/len(rs):+.2f}%")
