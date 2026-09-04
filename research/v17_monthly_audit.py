# -*- coding: utf-8 -*-
"""v17 monthly distribution audit (v14 lesson: check concentration).
Verify +6.47% isn't driven by one month/year."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_v17_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

# yearly concentration
by_y = defaultdict(list)
for t in trades:
    by_y[str(t["entry_date"])[:4]].append(t["net_pnl_pct"])
print("=== 逐年 ===")
for y in ("2023", "2024", "2025", "2026"):
    rs = by_y.get(y, [])
    if rs:
        w = sum(1 for x in rs if x > 0)
        print(f"  {y}: n={len(rs)} ({100*len(rs)/len(trades):.0f}%) WR={100*w/len(rs):.0f}% avg={sum(rs)/len(rs):+.2f}%")

# monthly (2024 detail - is it one month?)
print("\n=== 2024 月度（检查集中度）===")
by_m24 = defaultdict(list)
for t in trades:
    if str(t["entry_date"]).startswith("2024"):
        by_m24[str(t["entry_date"])[:6]].append(t["net_pnl_pct"])
for m in sorted(by_m24):
    rs = by_m24[m]
    print(f"  {m}: n={len(rs)} avg={sum(rs)/len(rs):+.2f}%")

# 2026 monthly
print("\n=== 2026 月度 ===")
by_m26 = defaultdict(list)
for t in trades:
    if str(t["entry_date"]).startswith("2026"):
        by_m26[str(t["entry_date"])[:6]].append(t["net_pnl_pct"])
for m in sorted(by_m26):
    rs = by_m26[m]
    print(f"  {m}: n={len(rs)} avg={sum(rs)/len(rs):+.2f}%")

# quarter concentration
print("\n=== 季度集中度 ===")
by_q = defaultdict(list)
for t in trades:
    m = str(t["entry_date"])[:6]
    q = m[:4] + "Q" + str((int(m[4:6]) - 1) // 3 + 1)
    by_q[q].append(t["net_pnl_pct"])
for q in sorted(by_q):
    rs = by_q[q]
    if len(rs) >= 20:
        print(f"  {q}: n={len(rs)} avg={sum(rs)/len(rs):+.2f}%")
