# -*- coding: utf-8 -*-
"""事件腿集中度分析：202402 单月 1433 笔的影响 + 分散约束（按月/周/信号密度 cap）效果"""
import csv, os, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

p = r"E:\test\smc_project\research\combo_v20f_trades.csv"
rows = []
with open(p, encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        try:
            r["net_pnl_pct"] = float(r["net_pnl_pct"]) if r["net_pnl_pct"] not in (None, "", "None") else None
        except Exception:
            r["net_pnl_pct"] = None
        if r["net_pnl_pct"] is not None and r.get("entry_date"):
            rows.append(r)

def stats(pn):
    if not pn:
        return None
    n = len(pn)
    mean = sum(pn) / n
    wins = [x for x in pn if x > 0]
    losses = [x for x in pn if x <= 0]
    pf = sum(wins) / abs(sum(losses)) if losses else 99.0
    return {"n": n, "avg": mean, "win": len(wins) / n, "pf": pf}

def fmt(s):
    return "n=%d avg=%+.2f%% wr=%.0f%% PF=%.2f" % (s["n"], s["avg"], s["win"]*100, s["pf"]) if s else "n=0"

# 按月分布
by_month = defaultdict(list)
for r in rows:
    by_month[r["entry_date"][:6]].append(r)
print("总笔数:", len(rows))
print("月份数:", len(by_month))
# 集中度：最大单月占比
mx_m = max(by_month, key=lambda m: len(by_month[m]))
mx_n = len(by_month[mx_m])
print("最大单月: %s %d 笔 (%.1f%%)" % (mx_m, mx_n, mx_n/len(rows)*100))
# top5 月份
top5 = sorted(by_month.items(), key=lambda kv: -len(kv[1]))[:5]
print("Top5 月份:", [(m, len(v)) for m, v in top5])

# 去掉 202402 后整体
rest = [r for r in rows if r["entry_date"][:6] != "202402"]
print("\n=== 含 vs 不含 202402 ===")
print("含202402:", fmt(stats([r["net_pnl_pct"] for r in rows])))
print("不含202402:", fmt(stats([r["net_pnl_pct"] for r in rest])))
if rest:
    r0 = stats([r["net_pnl_pct"] for r in rows])
    r1 = stats([r["net_pnl_pct"] for r in rest])
    print("均值变化: %+.2fpp" % ((r1["avg"] - r0["avg"]) * 100))

# 分散约束：每月 cap（保留该月 rank 最高的前 N 笔）
print("\n=== 按月 cap 分散约束 ===")
for cap in (300, 500, 800):
    sel = []
    for m, v in by_month.items():
        v_sorted = sorted(v, key=lambda r: -(r.get("rank_score") if r.get("rank_score") is not None else 0))
        sel.extend(v_sorted[:cap])
    s = stats([r["net_pnl_pct"] for r in sel])
    print("cap=%d: %s" % (cap, fmt(s)))
