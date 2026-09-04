# -*- coding: utf-8 -*-
"""生成 v20d 组合 dashboard（逐年/逐月统计，用分层 TP/SL 数据）"""
import csv, io, json, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_v20d_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

yearly = defaultdict(list)
monthly = defaultdict(list)
for t in trades:
    y = str(t["entry_date"])[:4]
    m = str(t["entry_date"])[:6]
    yearly[y].append(t["net_pnl_pct"])
    monthly[m].append(t["net_pnl_pct"])


def stats(rs):
    if not rs:
        return {"n": 0, "wr": 0, "avg": 0, "cum": 0, "pf": 0}
    wins = [x for x in rs if x > 0]
    losses = [x for x in rs if x <= 0]
    return {"n": len(rs), "wr": round(100 * len(wins) / len(rs), 1),
            "avg": round(sum(rs) / len(rs), 2), "cum": round(sum(rs), 1),
            "pf": round(sum(wins) / abs(sum(losses)), 2) if losses else 99}


y_out = []
for y in sorted(yearly):
    s = stats(yearly[y])
    s["year"] = y
    y_out.append(s)
m_out = []
for m in sorted(monthly):
    s = stats(monthly[m])
    s["month"] = m
    m_out.append(s)

dash = {
    "production_strategy": "COMBO_SMC_EVENT",
    "version": "V20D_TIERED",
    "total_trades": len(trades),
    "yearly": y_out,
    "monthly": m_out,
    "note": "v20d: 事件腿分层 TP/SL（TP1 30% → TP2 → TP3 runner）+ 延续固定10日 + SMC",
}
with open(r"E:\test\smc_project\research\combo_dashboard.json", "w", encoding="utf-8") as fh:
    json.dump(dash, fh, ensure_ascii=False, indent=2)
print("v20d dashboard 生成:")
for y in y_out:
    print(f"  {y['year']}: n={y['n']} WR={y['wr']}% avg={y['avg']:+.2f}% cum={y['cum']:+.1f}% PF={y['pf']}")
print(f"总: {len(trades)} 笔")
