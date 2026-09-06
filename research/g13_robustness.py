# -*- coding: utf-8 -*-
"""G13: 稳健性切片 —— 剔除最好1月/最好5%交易 + 月度HHI（防单月支撑收益）"""
import csv, os, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def load(p):
    with open(p, encoding="utf-8-sig") as fh:
        return [r for r in csv.DictReader(fh) if r.get("net_pnl_pct") not in (None, "", "None")]

smc = load(r"E:\test\smc_project\wdh\W1D1D4_trades.csv")
print(f"SMC trades: {len(smc)}")

def pf(pn):
    if not pn:
        return 0, 0
    wins = [x for x in pn if x > 0]
    losses = [x for x in pn if x <= 0]
    p = sum(wins) / abs(sum(losses)) if losses else 99
    return p, sum(pn) / len(pn)

pn_all = [float(r["net_pnl_pct"]) for r in smc]
p0, a0 = pf(pn_all)
print(f"全样本: n={len(pn_all)} avg={a0:+.2f}% PF={p0:.2f}")

# 月度贡献 + HHI
by_m = defaultdict(list)
for r in smc:
    by_m[r["entry_date"][:6]].append(float(r["net_pnl_pct"]))
month_pnl = {m: sum(v) for m, v in by_m.items()}
tot = sum(abs(v) for v in month_pnl.values())
h = sum((abs(v)/tot)**2 for v in month_pnl.values()) if tot else 0
print(f"月度HHI: {h:.3f} (目标<0.15) | 月度数: {len(month_pnl)}")
# 剔除最好月
worst_excl = max(month_pnl, key=month_pnl.get)
pn_x1 = [x for r in smc for x in ([float(r['net_pnl_pct'])] if r['entry_date'][:6] != worst_excl else [])]
p1, a1 = pf(pn_x1)
print(f"剔除最好月({worst_excl}): n={len(pn_x1)} avg={a1:+.2f}% PF={p1:.2f}")
# 剔除 top-5% 交易
sorted_pn = sorted(pn_all, reverse=True)
cut5 = int(len(sorted_pn) * 0.05)
pn_x5 = sorted_pn[cut5:]
p2, a2 = pf(pn_x5)
print(f"剔除top5%交易: n={len(pn_x5)} avg={a2:+.2f}% PF={p2:.2f}")

ok_m = h < 0.15 and p1 > 1.5
print(f"\n验收: 月度HHI<0.15 且 剔最好月PF>1.5 → {'通过 ✅' if ok_m else '未过 ❌'}")
