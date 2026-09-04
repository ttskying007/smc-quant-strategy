# -*- coding: utf-8 -*-
"""v14 honest check: event-leg distribution (yearly/monthly) + SMC leg contribution.
Verify the +10.87% isn't driven by one year/month."""
import csv, io, json, os, sys
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_v14_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

smc = [t for t in trades if t.get("src") != "EVENT"]
ev = [t for t in trades if t.get("src") == "EVENT"]
print(f"总交易: {len(trades)}, SMC腿: {len(smc)} ({100*len(smc)/len(trades):.1f}%), 事件腿: {len(ev)}")
print(f"SMC 腿占比: {100*len(smc)/len(trades):.1f}% —— 贡献极小，需评估")

# event leg yearly detail
print("\n=== 事件腿逐年 ===")
by_y = defaultdict(list)
for t in ev:
    by_y[str(t["entry_date"])[:4]].append(t["net_pnl_pct"])
for y in ("2023", "2024", "2025", "2026"):
    rs = by_y.get(y, [])
    if rs:
        w = sum(1 for x in rs if x > 0)
        print(f"  {y}: n={len(rs)} ({100*len(rs)/len(ev):.0f}%) WR={100*w/len(rs):.0f}% avg={sum(rs)/len(rs):+.2f}%")

# event leg monthly (2025/2026 detail - small samples)
print("\n=== 事件腿 2025/2026 月度 ===")
by_m = defaultdict(list)
for t in ev:
    m = str(t["entry_date"])[:6]
    if m >= "202501":
        by_m[m].append(t["net_pnl_pct"])
for m in sorted(by_m):
    rs = by_m[m]
    print(f"  {m}: n={len(rs)} avg={sum(rs)/len(rs):+.2f}%")

# event leg contribution to total pnl
print("\n=== 盈亏贡献 ===")
ev_pnl = sum(t["net_pnl_pct"] for t in ev)
smc_pnl = sum(t["net_pnl_pct"] for t in smc)
print(f"事件腿累计: {ev_pnl:+.0f}% ({100*ev_pnl/(ev_pnl+smc_pnl):.1f}% 贡献)")
print(f"SMC腿累计: {smc_pnl:+.0f}% ({100*smc_pnl/(ev_pnl+smc_pnl):.1f}% 贡献)")

# SMC leg yearly
print("\n=== SMC 腿逐年 ===")
by_ys = defaultdict(list)
for t in smc:
    by_ys[str(t["entry_date"])[:4]].append(t["net_pnl_pct"])
for y in ("2024", "2025", "2026"):
    rs = by_ys.get(y, [])
    if rs:
        print(f"  {y}: n={len(rs)} avg={sum(rs)/len(rs):+.2f}%")
