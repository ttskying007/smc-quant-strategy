# -*- coding: utf-8 -*-
"""组合每日开仓密度（实盘资金规模需求估算）"""
import csv, io, json, os, sys
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        trades.append(r)

by_day = Counter(str(t["entry_date"]) for t in trades)
days = sorted(by_day.keys())
vals = [by_day[d] for d in days]
print(f"总交易日: {len(days)} | 总交易: {len(trades)}")
print(f"每日开仓: min={min(vals)} med={sorted(vals)[len(vals)//2]} max={max(vals)} avg={len(trades)/len(days):.1f}")

# per year
by_y = defaultdict(Counter)
for t in trades:
    by_y[str(t["entry_date"])[:4]][str(t["entry_date"])] += 1
print("\n=== 逐年日均开仓 ===")
for y in ("2024", "2025", "2026"):
    c = by_y.get(y, Counter())
    if c:
        d = len(c)
        print(f"  {y}: 日均 {sum(c.values())/d:.1f} 笔（{d} 天）")

# estimate capital: avg position ~1/N equal weight. If 10 positions held avg 15d, daily new ~3-4
print("\n=== 资金规模估算（等权，平均持仓天数约 12 日）===")
daily_new = len(trades) / len(days)
avg_hold = (2361 * 10 + 4958 * 15 + 113 * 40) / len(trades)
est_positions = daily_new * avg_hold
print(f"日均新开仓: {daily_new:.1f} 笔 | 平均持有: {avg_hold:.0f} 日 | 估算同时持仓: ~{est_positions:.0f} 只")
print(f"若每只 10 万 → 需资金 ~{est_positions*10:.0f} 万")
print(f"若每只 5 万 → 需资金 ~{est_positions*5:.0f} 万")
