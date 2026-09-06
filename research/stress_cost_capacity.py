# -*- coding: utf-8 -*-
"""生产门禁 P1: 事件腿成本压力测试 —— FEE 1x/2x/3x 后 PF/avg 变化
+ 组合容量压力（500/300/100/50 同日限开仓数）
"""
import csv, os, random, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CSV = r"E:\test\smc_project\research\combo_v20f_trades.csv"
rows = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig")) if r.get("src") == "EVENT"
        and r.get("net_pnl_pct") not in (None, "", "None")]
print(f"事件腿: {len(rows)}")

def pf_avg(pn):
    if not pn:
        return 0, 0
    w = [x for x in pn if x > 0]; l = [x for x in pn if x <= 0]
    return (sum(w)/abs(sum(l)) if l else 99, sum(pn)/len(pn))

# 1. 成本压力：CSV net_pnl 已含 FEE=0.2（1x）；2x/3x 额外扣
# 原始 gross ≈ net + FEE（gen_v20f net = gross - FEE）
pn_1x = [float(r["net_pnl_pct"]) for r in rows]
gross = [x + 0.20 for x in pn_1x]  # 近似 gross
print("\n=== 成本压力（gross 还原后扣不同费用）===")
for mult, fee in ((1, 0.20), (2, 0.40), (3, 0.60)):
    pn = [g - fee for g in gross]
    p, a = pf_avg(pn)
    print(f"  FEE {fee:.2f} ({mult}x): n={len(pn)} avg={a:+.2f}% PF={p:.2f}")
p1, a1 = pf_avg(pn_1x)
p3, a3 = pf_avg([g - 0.60 for g in gross])
print(f"\n验收: 3x成本 PF {p3:.2f} > 1.5 → {'✅' if p3 > 1.5 else '❌'} (1x {p1:.2f} → 3x {p3:.2f})")

# 2. 组合容量压力：同日最多 N 笔开仓（按 entry_date 分组，超限跳过 rank 低者）
print("\n=== 组合容量压力（同日限开仓数）===")
by_day = defaultdict(list)
for r in rows:
    by_day[r["entry_date"]].append(float(r["net_pnl_pct"]))
for cap in (500, 300, 100, 50):
    kept = []
    for day, pn in by_day.items():
        # 同日超限：保留前 cap 笔（无 rank 排序信息，按出现顺序）
        kept.extend(pn[:cap])
    p, a = pf_avg(kept)
    print(f"  同日容量 {cap}: n={len(kept)} avg={a:+.2f}% PF={p:.2f}")
# 全市场容量 3000（无限制近似）
pn_all = [x for day in by_day for x in by_day[day][:3000]]
p_a, a_a = pf_avg(pn_all)
print(f"\n验收: 容量50 PF {pf_avg([x for day in by_day for x in by_day[day][:50]])[0]:.2f} > 1.5 → "
      f"{'✅' if pf_avg([x for day in by_day for x in by_day[day][:50]])[0] > 1.5 else '❌'}")
