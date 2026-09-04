# -*- coding: utf-8 -*-
"""v8 monthly loss analysis: which months lose, relation to market regime.
Goal: understand strategy boundary (per user: 每年每月的情况)."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_v8_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

by_m = defaultdict(list)
for t in trades:
    by_m[str(t["entry_date"])[:6]].append(t["net_pnl_pct"])

print("=== v8 逐月（亏损月标记）===")
print(f"{'月':<8} {'n':>5} {'胜率%':>6} {'avg%':>8} {'累计%':>9}")
losing = []
for m in sorted(by_m):
    rs = by_m[m]
    w = sum(1 for x in rs if x > 0)
    avg = sum(rs) / len(rs)
    cum = sum(rs)
    flag = " <<< 亏损" if avg < 0 else ""
    if avg < 0:
        losing.append(m)
    if m >= "202401":
        print(f"{m:<8} {len(rs):>5} {100*w/len(rs):>5.0f}% {avg:>+7.2f}% {cum:>+8.0f}{flag}")

print(f"\n亏损月: {losing}")
# by year, losing months
by_year_loss = defaultdict(list)
for m in losing:
    by_year_loss[m[:4]].append(m)
for y in sorted(by_year_loss):
    print(f"  {y}: {by_year_loss[y]}")

# quarterly view
print("\n=== 季度视图 ===")
by_q = defaultdict(list)
for t in trades:
    m = str(t["entry_date"])[:6]
    q = m[:4] + "Q" + str((int(m[4:6]) - 1) // 3 + 1)
    by_q[q].append(t["net_pnl_pct"])
for q in sorted(by_q):
    rs = by_q[q]
    avg = sum(rs) / len(rs)
    w = sum(1 for x in rs if x > 0)
    flag = " <<< 亏损" if avg < 0 else ""
    print(f"  {q}: n={len(rs)} WR={100*w/len(rs):.0f}% avg={avg:+.2f}%{flag}")
