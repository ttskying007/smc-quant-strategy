# -*- coding: utf-8 -*-
"""费用敏感性：v20c 组合在更高交易成本下是否仍有效（实盘可行性）
当前 fee 0.20%（每笔双边）。测试 0.30%/0.40%/0.50%"""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        trades.append(r)

# trades store net (already minus 0.20). Reconstruct gross by adding back 0.20.
gross = [dict(t, net_pnl_pct=float(t["net_pnl_pct"]) + 0.20) for t in trades]


def report(label, rs):
    if len(rs) < 300:
        print(f"{label}: n={len(rs)} (过小)")
        return
    for t in rs:
        t["t1_violation"] = "False"
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(rs)
    o = gate["overall"]
    line = f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']}"
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if t["year"] == y]
        if ys:
            line += f" | {y}:{sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%"
    print(line)


print("\n=== v20c 费用敏感性 ===")
for fee in (0.20, 0.30, 0.40, 0.50):
    rs = [dict(t, net_pnl_pct=round(t["net_pnl_pct"] - fee, 4)) for t in gross]
    report(f"fee {fee}%", rs)
