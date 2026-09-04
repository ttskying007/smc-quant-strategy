# -*- coding: utf-8 -*-
"""2023 弱势归因：事件腿 vs 延续腿在 2023 的表现分布"""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

# by year + src
by_ys = defaultdict(list)
for t in trades:
    by_ys[(str(t["entry_date"])[:4], t.get("src", "?"))].append(t["net_pnl_pct"])

print("=== 逐年 × 腿 ===")
for y in ("2023", "2024", "2025", "2026"):
    line = f"{y}: "
    for src in ("EVENT", "CONT", "SMC"):
        rs = by_ys.get((y, src), [])
        if rs:
            w = sum(1 for x in rs if x > 0)
            line += f" {src}(n={len(rs)} avg={sum(rs)/len(rs):+.2f}% WR={100*w/len(rs):.0f}%)"
    print(line)

# 2023 monthly
by_m = defaultdict(list)
for t in trades:
    if str(t["entry_date"]).startswith("2023"):
        by_m[str(t["entry_date"])[:6]].append(t["net_pnl_pct"])
print("\n=== 2023 月度 ===")
for m in sorted(by_m):
    rs = by_m[m]
    print(f"  {m}: n={len(rs)} avg={sum(rs)/len(rs):+.2f}%")
