# -*- coding: utf-8 -*-
"""v_monthly_walk.py —— 按月全量交易复计 (EVENT 腿)
目的: 用户对连续亏损压力最大的一个 audit point 就是,
"某个时间段系统把 user 扔了; 为什么?"

导出:
  每月份: n_trades, n_closed, avg_net_pct, PF, wr, top11个 原因分布
输入: combo_v20f_trades.csv
"""
import csv, json, io, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

data = []
with open(r"research/combo_v20f_trades.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r.get("src") != "EVENT":
            continue
        # 事件日期（买日）→ 月份
        buy_d = r.get("buy_date") or ""
        # 我的 buy_date 来自 source.t (YYYYMMDD 400位) → month = 前 6 位
        month = (buy_d[:4] + '-' + buy_d[4:6]) if len(buy_d) >= 6 else buy_d[:6]
        if not month:
            continue
        net = float(r.get("net_pnl_pct") or 0)
        closed = r.get("reason") and r.get("reason") != "OPEN"
        r["_net"] = net
        r["_closed"] = closed
        data.append(r)

by_month = defaultdict(list)
for r in data:
    by_month[r.get("buy_date", "")[:7]].append(r)

# summary rows
summary = []
for m in sorted(by_month.keys()):
    rows = by_month[m]
    closes = [x for x in rows if x["_closed"]]
    pnls = [x["_net"] for x in closes]
    if not closes:
        continue
    wins = sum(1 for x in closes if x["_net"] > 0)
    mean = sum(pnls) / len(pnls)
    pos = sum(p for p in pnls if p > 0)
    neg = sum(-p for p in pnls if p < 0)
    pf = (pos / neg) if neg else float("inf")
    summary.append({"month": m, "n_closed": len(closes),
                    "n_full": len(rows),
                    "avg_pct": round(mean, 2),
                    "pf": round(pf, 2), "wr_pct": round(wins / len(closes) * 100, 1)})

os.makedirs("research/handover", exist_ok=True)
out_fp = "research/handover/monthly_breakdown.json"
json.dump({"generated": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
           "note": "EVENT 腿逐月统计 (v20f combo), n_total=%d" % len(data),
           "months": summary},
          open(out_fp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# stdout
print("EVENT 腿逐月汇总 (v20f)")
print(f"{'月份':10s} {'N全':>5s} {'N闭':>5s} {'平均%':>8s} {'PF':>6s} {'WR%':>6s}")
for s in summary:
    print(f"  {s['month']:10s} {s['n_full']:>5d} {s['n_closed']:>5d} "
          f"{s['avg_pct']:>8.2f} {s['pf']:>6.2f} {s['wr_pct']:>6.1f}")
print(f"\nwrote {out_fp}")
print(f"覆盖月份: {summary[0]['month']} -> {summary[-1]['month']} ({len(summary)} 月)")
