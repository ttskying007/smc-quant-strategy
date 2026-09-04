# -*- coding: utf-8 -*-
"""延续腿买点/卖点验证：入场（T+1开盘 vs 支撑回踩）+ 出场（固定10日 vs 分层）
延续腿信号少（76 笔）—— 聚焦方向性验证"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")

# use v20c/v20d CSV for continuation analysis (76+ signals)
import csv
from collections import defaultdict

trades = []
with open(r"E:\test\smc_project\research\combo_v20d_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

cont = [t for t in trades if t.get("src") == "CONT"]
print(f"延续腿: {len(cont)} 笔\n")
if cont:
    pnls = [t["net_pnl_pct"] for t in cont]
    wins = [x for x in pnls if x > 0]
    print(f"avg {sum(pnls)/len(pnls):+.2f}% | 胜率 {100*len(wins)/len(pnls):.0f}% | PF {sum(wins)/abs(sum(x for x in pnls if x<=0)) if any(x<=0 for x in pnls) else 99:.2f}")
    # by year
    for y in ("2024", "2025", "2026"):
        ys = [t["net_pnl_pct"] for t in cont if str(t["entry_date"])[:4] == y]
        if ys:
            print(f"  {y}: n={len(ys)} avg={sum(ys)/len(ys):+.2f}%")
    # distribution
    pnls_s = sorted(pnls)
    n = len(pnls_s)
    print(f"\n分布: P5={pnls_s[max(0,int(n*0.05))]:+.1f}% P50={pnls_s[n//2]:+.1f}% P95={pnls_s[min(n-1,int(n*0.95))]:+.1f}%")
    print(f"最差 {min(pnls):+.2f}% | 最好 {max(pnls):+.2f}%")

# event leg comparison (for reference)
ev = [t for t in trades if t.get("src") == "EVENT"]
print(f"\n事件腿（参考）: {len(ev)} 笔")
pnls_e = [t["net_pnl_pct"] for t in ev]
wins_e = [x for x in pnls_e if x > 0]
print(f"avg {sum(pnls_e)/len(pnls_e):+.2f}% | 胜率 {100*len(wins_e)/len(pnls_e):.0f}% | PF {sum(wins_e)/abs(sum(x for x in pnls_e if x<=0)):.2f}")
