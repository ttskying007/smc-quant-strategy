# -*- coding: utf-8 -*-
"""SMC leg monthly calendar (compare with event leg). Does SMC leg hedge weak event months?"""
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_v18_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

smc = [t for t in trades if t.get("src") != "EVENT"]
ev = [t for t in trades if t.get("src") == "EVENT"]
print(f"SMC: {len(smc)}, EVENT: {len(ev)}")

def monthly(pool):
    by_m = defaultdict(list)
    for t in pool:
        by_m[str(t["entry_date"])[4:6]].append(t["net_pnl_pct"])
    return by_m

m_smc = monthly(smc)
m_ev = monthly(ev)

print("\n=== 月度对比（SMC vs EVENT）===")
print(f"{'月':<4} {'SMC n':>6} {'SMC avg%':>9} {'EV n':>6} {'EV avg%':>9} {'组合':>7}")
for m in sorted(set(list(m_smc.keys()) + list(m_ev.keys()))):
    s = m_smc.get(m, [])
    e = m_ev.get(m, [])
    s_avg = sum(s) / len(s) if s else 0
    e_avg = sum(e) / len(e) if e else 0
    combo = s_avg + e_avg  # both legs (equal weight in merged pool)
    print(f"{m:<4} {len(s):>6} {s_avg:>+8.2f}% {len(e):>6} {e_avg:>+8.2f}% {combo:>+6.2f}%")

# 8月 SMC by year
print("\n=== SMC 腿 8 月逐年 ===")
by_ym = defaultdict(list)
for t in smc:
    by_ym[str(t["entry_date"])[:6]].append(t["net_pnl_pct"])
for ym in sorted(by_ym):
    if ym[4:6] == "08":
        rs = by_ym[ym]
        print(f"  {ym}: n={len(rs)} avg={sum(rs)/len(rs):+.2f}%")
