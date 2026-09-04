# -*- coding: utf-8 -*-
"""三腿相关性分析：事件/延续/SMC 月度平均收益相关性（统计确认互补）"""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

# monthly avg by leg
by_leg_m = defaultdict(lambda: defaultdict(list))
for t in trades:
    m = str(t["entry_date"])[:6]
    if m < "202309":
        continue
    src = t.get("src", "SMC")
    by_leg_m[src][m].append(t["net_pnl_pct"])

legs = {}
for src in ("EVENT", "CONT", "SMC"):
    monthly = {}
    for m, rs in by_leg_m[src].items():
        if len(rs) >= 3:
            monthly[m] = sum(rs) / len(rs)
    legs[src] = monthly
    print(f"{src}: {len(monthly)} 月")

# correlation
def corr(a, b):
    keys = [k for k in a if k in b]
    if len(keys) < 10:
        return None
    va = [a[k] for k in keys]
    vb = [b[k] for k in keys]
    ma = sum(va) / len(va)
    mb = sum(vb) / len(vb)
    cov = sum((va[i] - ma) * (vb[i] - mb) for i in range(len(va)))
    sa = (sum((x - ma) ** 2 for x in va) ** 0.5)
    sb = (sum((x - mb) ** 2 for x in vb) ** 0.5)
    if sa == 0 or sb == 0:
        return None
    return cov / (sa * sb)

print("\n=== 三腿月度收益相关性 ===")
pairs = [("EVENT", "CONT"), ("EVENT", "SMC"), ("CONT", "SMC")]
for a, b in pairs:
    c = corr(legs[a], legs[b])
    if c is not None:
        interp = "低相关（互补）" if abs(c) < 0.3 else ("正相关（同向）" if c > 0 else "负相关（对冲）")
        print(f"  {a} vs {b}: r={c:+.2f}（{interp}）")
    else:
        print(f"  {a} vs {b}: 样本不足")
