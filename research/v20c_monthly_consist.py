# -*- coding: utf-8 -*-
"""v20c 月度一致性：每月正收益比例（稳定性最终确认）"""
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
pos = [m for m in months if sum(by_m[m]) / len(by_m[m]) > 0]
neg = [m for m in months if sum(by_m[m]) / len(by_m[m]) <= 0]
print(f"总月份: {len(months)} | 正月份: {len(pos)} ({100*len(pos)/len(months):.0f}%) | 负月份: {len(neg)}")

print("\n=== 逐年月度一致性 ===")
for y in ("2024", "2025", "2026"):
    ms = [m for m in months if m.startswith(y)]
    ps = [m for m in ms if sum(by_m[m]) / len(by_m[m]) > 0]
    if ms:
        print(f"  {y}: {len(ps)}/{len(ms)} 月正 ({100*len(ps)/len(ms):.0f}%)")

print("\n=== 负月份明细 ===")
for m in neg:
    rs = by_m[m]
    print(f"  {m}: n={len(rs)} avg={sum(rs)/len(rs):+.2f}%")
