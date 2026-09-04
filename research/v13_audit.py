# -*- coding: utf-8 -*-
"""v13 audit: leg distribution + yearly concentration check (v14 lesson)."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_v13_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

smc = [t for t in trades if t.get("src") != "EVENT"]
ev = [t for t in trades if t.get("src") == "EVENT"]
print(f"总: {len(trades)} | SMC腿: {len(smc)} ({100*len(smc)/len(trades):.1f}%) | 事件腿: {len(ev)}")


def yearly_detail(label, pool):
    by = defaultdict(list)
    for t in pool:
        by[str(t["entry_date"])[:4]].append(t["net_pnl_pct"])
    print(f"\n=== {label} 逐年 ===")
    for y in ("2023", "2024", "2025", "2026"):
        rs = by.get(y, [])
        if rs:
            w = sum(1 for x in rs if x > 0)
            print(f"  {y}: n={len(rs)} ({100*len(rs)/len(pool):.0f}%) WR={100*w/len(rs):.0f}% avg={sum(rs)/len(rs):+.2f}%")


yearly_detail("SMC腿", smc)
yearly_detail("事件腿", ev)

# event leg monthly concentration (2026)
print("\n=== 事件腿 2026 月度 ===")
by_m = defaultdict(list)
for t in ev:
    if str(t["entry_date"]).startswith("2026"):
        by_m[str(t["entry_date"])[:6]].append(t["net_pnl_pct"])
for m in sorted(by_m):
    rs = by_m[m]
    print(f"  {m}: n={len(rs)} avg={sum(rs)/len(rs):+.2f}%")

# concentration ratio: largest year share
print("\n=== 集中度检查 ===")
for label, pool in (("SMC", smc), ("EVENT", ev)):
    by = defaultdict(int)
    for t in pool:
        by[str(t["entry_date"])[:4]] += 1
    if by:
        top = max(by, key=by.get)
        print(f"  {label}: 最大年 {top} 占 {100*by[top]/len(pool):.0f}%（n={by[top]}/{len(pool)}）")
