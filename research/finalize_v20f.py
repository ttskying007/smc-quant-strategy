# -*- coding: utf-8 -*-
"""生成 v20f dashboard（逐年/逐月/逐个股统计）"""
import csv, io, json, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

yearly = defaultdict(list)
monthly = defaultdict(list)
by_symbol = defaultdict(list)
for t in trades:
    y = str(t["entry_date"])[:4]
    m = str(t["entry_date"])[:6]
    sym = str(t["symbol"])
    yearly[y].append(t["net_pnl_pct"])
    monthly[m].append(t["net_pnl_pct"])
    by_symbol[sym].append(t["net_pnl_pct"])


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
sym_out = []
for sym, rs in sorted(by_symbol.items(), key=lambda kv: -len(kv[1])):
    s = stats(rs)
    s["symbol"] = sym
    sym_out.append(s)

dash = {
    "production_strategy": "COMBO_SMC_EVENT",
    "version": "V20F_FIXED",
    "total_trades": len(trades),
    "yearly": y_out,
    "monthly": m_out,
    "by_symbol": sym_out[:100],
    "note": "v20f: 事件腿(无泄漏7特征+新SL) + 回踩买点 + 分层TP/SL + 延续腿(VWAP10%+新鲜度)",
}
with open(r"E:\test\smc_project\research\combo_dashboard.json", "w", encoding="utf-8") as fh:
    json.dump(dash, fh, ensure_ascii=False, indent=2)
print("v20f dashboard 生成:")
for y in y_out:
    print(f"  {y['year']}: n={y['n']} WR={y['wr']}% avg={y['avg']:+.2f}% cum={y['cum']:+.1f}% PF={y['pf']}")
print(f"总: {len(trades)} 笔 | 个股: {len(by_symbol)} 只")

# monthly 2026
print("\n2026 逐月:")
for m in [x for x in m_out if x["month"].startswith("2026")]:
    print(f"  {m['month']}: n={m['n']} avg={m['avg']:+.2f}% WR={m['wr']}%")
