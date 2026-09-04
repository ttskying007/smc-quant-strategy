# -*- coding: utf-8 -*-
"""Combo weighting sensitivity: SMC leg vs event leg allocation.
Blend yearly returns at different weights; verify yearly stays positive."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# SMC leg trades (UPTREND/MARKUP, from v10 run logic - reuse combo_v10 SMC part)
# Simplest: v10 combined has src field; separate by src
trades = []
with open(r"E:\test\smc_project\research\combo_v10_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        r["src"] = r.get("src", "")
        trades.append(r)

smc = [t for t in trades if t["src"] != "EVENT"]
ev = [t for t in trades if t["src"] == "EVENT"]
print(f"SMC: {len(smc)}, EVENT: {len(ev)}")


def yearly(pool):
    by = defaultdict(list)
    for t in pool:
        by[str(t["entry_date"])[:4]].append(t["net_pnl_pct"])
    res = {}
    for y in ("2024", "2025", "2026"):
        rs = by.get(y, [])
        if rs:
            res[y] = sum(rs) / len(rs)
    return res


y_smc = yearly(smc)
y_ev = yearly(ev)
print("SMC yearly:", {y: f"{v:+.2f}%" for y, v in y_smc.items()})
print("EVENT yearly:", {y: f"{v:+.2f}%" for y, v in y_ev.items()})

print("\n=== 权重敏感性（SMC 权重 vs 事件权重）===")
print(f"{'SMC权重':<8} {'2024':>8} {'2025':>8} {'2026':>8} {'每年正?':>8}")
for w in (0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0):
    vals = {}
    ok = True
    for y in ("2024", "2025", "2026"):
        a = y_smc.get(y, 0)
        b = y_ev.get(y, 0)
        blended = w * a + (1 - w) * b
        vals[y] = blended
        if blended <= 0:
            ok = False
    print(f"{w:<8.1f} {vals['2024']:>+7.2f}% {vals['2025']:>+7.2f}% {vals['2026']:>+7.2f}% {'✅' if ok else '❌'}")
