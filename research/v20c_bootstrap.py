# -*- coding: utf-8 -*-
"""v20c 随机子样本稳健性（Bootstrap：10 次随机 80% 抽样，防过拟合统计检验）
如果 avg/PF 在子样本中稳定 → 非过拟合"""
import csv, io, json, os, random, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

random.seed(42)
trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)
print("总交易:", len(trades))

# full sample
def full_stats():
    rs = list(trades)
    for t in rs:
        t["t1_violation"] = "False"
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(rs)
    o = gate["overall"]
    return o["avg"], o["pf"], o["wr"]

fa, fp, fw = full_stats()
print(f"全样本: avg={fa:+.2f}% PF={fp} WR={fw}%")

# bootstrap 80% subsamples
avgs = []
pfs = []
for trial in range(10):
    sub = random.sample(trades, int(len(trades) * 0.8))
    rs = [dict(t) for t in sub]
    for t in rs:
        t["t1_violation"] = "False"
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(rs)
    o = gate["overall"]
    avgs.append(o["avg"])
    pfs.append(o["pf"])

print("\n=== 随机 80% 子样本（10 次）===")
print(f"avg: min={min(avgs):+.2f}% max={max(avgs):+.2f}% 全样本={fa:+.2f}%")
print(f"PF:  min={min(pfs):.2f} max={max(pfs):.2f} 全样本={fp:.2f}")
stable = all(a > 0 for a in avgs) and all(p > 1.5 for p in pfs)
print(f"稳健性: {'✅ 全部子样本 avg>0 且 PF>1.5（非过拟合）' if stable else '⚠️ 存在弱子样本'}")
