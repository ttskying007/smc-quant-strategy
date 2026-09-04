# -*- coding: utf-8 -*-
"""组合权重优化：反转腿权重 1.0，延续腿权重 0.5/0.7/0.8（半仓策略）
等权合并池中延续腿 avg 低稀释 → 权重调整看是否提升"""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

reversal = [t for t in trades if t.get("src") != "CONT"]
cont = [t for t in trades if t.get("src") == "CONT"]
print(f"反转 {len(reversal)} | 延续 {len(cont)}")


def report(label, rs, weight_map):
    """rs: list of (t, w) tuples."""
    out = []
    for t, w in rs:
        tt = dict(t)
        tt["net_pnl_pct"] = t["net_pnl_pct"] * w
        tt["w"] = w
        out.append(tt)
    if len(out) < 300:
        print(f"{label}: n={len(out)} (过小)")
        return
    for t in out:
        t["t1_violation"] = "False"
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(out)
    o = gate["overall"]
    # weighted avg
    tw = sum(t["w"] for t in out)
    wavg = sum(t["net_pnl_pct"] for t in out) / tw
    line = f"{label}: n={len(out)} avg={wavg:+.2f}% PF={o['pf']} WR={o['wr']}%"
    for y in ("2024", "2025", "2026"):
        ys = [t for t in out if t["year"] == y]
        if ys:
            yw = sum(t["w"] for t in ys)
            line += f" | {y}:{sum(t['net_pnl_pct'] for t in ys)/yw:+.2f}%"
    print(line)


print("\n=== v20c 权重优化 ===")
for w in (1.0, 0.8, 0.7, 0.5, 0.3):
    pool = [(t, 1.0) for t in reversal] + [(t, w) for t in cont]
    report(f"延续权重 {w}", pool, w)
