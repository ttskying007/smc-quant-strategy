# -*- coding: utf-8 -*-
"""v20c 风险调整指标：月度收益序列的波动率/夏普/Calmar"""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

by_m = defaultdict(list)
for t in trades:
    m = str(t["entry_date"])[:6]
    if m >= "202309":
        by_m[m].append(t["net_pnl_pct"])

monthly_avg = {m: sum(rs) / len(rs) for m, rs in by_m.items()}
vals = [monthly_avg[m] for m in sorted(monthly_avg)]
n = len(vals)
mean = sum(vals) / n
var = sum((x - mean) ** 2 for x in vals) / (n - 1)
std = var ** 0.5

print("=== v20c 月度风险指标 ===")
print(f"月数: {n}")
print(f"月度平均: {mean:+.2f}%")
print(f"月度波动率: {std:.2f}%")
print(f"夏普(月, rf=0): {mean/std:.2f}" if std else "波动率0")
# annualized
ann_mean = mean * 12
ann_std = std * (12 ** 0.5)
print(f"年化平均: {ann_mean:+.2f}% | 年化波动: {ann_std:.2f}% | 年化夏普: {ann_mean/ann_std:.2f}")

# max drawdown on monthly series
cum = 0
peak = 0
mdd = 0
for v in vals:
    cum += v
    if cum > peak:
        peak = cum
    dd = cum - peak
    if dd < mdd:
        mdd = dd
print(f"月度累计最大回撤: {mdd:+.2f}%")
print(f"Calmar(年化/回撤): {ann_mean/abs(mdd):.2f}" if mdd else "无回撤")

# monthly positive ratio
pos = sum(1 for v in vals if v > 0)
print(f"月度正收益比例: {100*pos/n:.0f}%")
