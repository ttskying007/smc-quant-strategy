# -*- coding: utf-8 -*-
"""v20c 月度集中度 + 回撤分析（v14 教训：确认不单月依赖）"""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

print("=== v20c 逐年 ===")
by_y = defaultdict(list)
for t in trades:
    by_y[str(t["entry_date"])[:4]].append(t["net_pnl_pct"])
for y in ("2023", "2024", "2025", "2026"):
    rs = by_y.get(y, [])
    if rs:
        w = sum(1 for x in rs if x > 0)
        print(f"  {y}: n={len(rs)} WR={100*w/len(rs):.0f}% avg={sum(rs)/len(rs):+.2f}%")

print("\n=== 2024 月度 ===")
by_m24 = defaultdict(list)
for t in trades:
    if str(t["entry_date"]).startswith("2024"):
        by_m24[str(t["entry_date"])[:6]].append(t["net_pnl_pct"])
for m in sorted(by_m24):
    rs = by_m24[m]
    print(f"  {m}: n={len(rs)} avg={sum(rs)/len(rs):+.2f}%")

print("\n=== 2025 月度 ===")
by_m25 = defaultdict(list)
for t in trades:
    if str(t["entry_date"]).startswith("2025"):
        by_m25[str(t["entry_date"])[:6]].append(t["net_pnl_pct"])
for m in sorted(by_m25):
    rs = by_m25[m]
    print(f"  {m}: n={len(rs)} avg={sum(rs)/len(rs):+.2f}%")

print("\n=== 2026 月度 ===")
by_m26 = defaultdict(list)
for t in trades:
    if str(t["entry_date"]).startswith("2026"):
        by_m26[str(t["entry_date"])[:6]].append(t["net_pnl_pct"])
for m in sorted(by_m26):
    rs = by_m26[m]
    print(f"  {m}: n={len(rs)} avg={sum(rs)/len(rs):+.2f}%")

print("\n=== 回撤分析（按交易日累计收益曲线）===")
# sort by date, cumulative
trades_sorted = sorted(trades, key=lambda t: t["entry_date"])
cum = 0.0
peak = 0.0
max_dd = 0.0
for t in trades_sorted:
    cum += t["net_pnl_pct"]
    if cum > peak:
        peak = cum
    dd = cum - peak
    if dd < max_dd:
        max_dd = dd
print(f"  累计收益: {cum:+.1f}%")
print(f"  峰值: {peak:+.1f}%")
print(f"  最大回撤: {max_dd:+.1f}%（按入场日累计）")

# worst months
print("\n=== 最差月份（整体）===")
by_m_all = defaultdict(list)
for t in trades:
    by_m_all[str(t["entry_date"])[:6]].append(t["net_pnl_pct"])
worst = sorted(by_m_all.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))[:8]
for m, rs in worst:
    if m >= "202309":
        print(f"  {m}: n={len(rs)} avg={sum(rs)/len(rs):+.2f}%")
