# -*- coding: utf-8 -*-
"""Generate combo strategy dashboard data (monthly table + current candidates JSON),
to be served as a standalone page /combo."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\research\combo_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        trades.append(r)

def stats(rs):
    n = len(rs)
    if not n:
        return None
    w = sum(1 for t in rs if float(t["net_pnl_pct"]) > 0)
    gp = sum(max(float(t["net_pnl_pct"]), 0) for t in rs)
    gl = abs(sum(min(float(t["net_pnl_pct"]), 0) for t in rs))
    return {"n": n, "wr": round(100 * w / n, 1), "avg": round(sum(float(t["net_pnl_pct"]) for t in rs) / n, 3),
            "cum": round(sum(float(t["net_pnl_pct"]) for t in rs), 1), "pf": round(gp / gl, 2) if gl else 0}

# monthly
by_m = defaultdict(list)
for t in trades:
    by_m[str(t["entry_date"])[:6]].append(t)
monthly = []
for m in sorted(by_m):
    s = stats(by_m[m])
    if s and m >= "202309":
        monthly.append({"month": m, **s})

# yearly
by_y = defaultdict(list)
for t in trades:
    by_y[str(t["entry_date"])[:4]].append(t)
yearly = [{"year": y, **stats(by_y[y])} for y in sorted(by_y) if stats(by_y[y])]

data = {"updated": "2026-08-17", "total_trades": len(trades), "yearly": yearly, "monthly": monthly,
        "note": "组合 = SMC三周期TP2-R20 + 内部人事件(增持/回购)；公告覆盖77%天数；等权合并池"}

out = r"E:\test\smc_project\research\combo_dashboard.json"
with open(out, "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)
print("dashboard data saved:", out)
print("yearly:", [(y["year"], y["n"], y["avg"]) for y in yearly])
print("monthly count:", len(monthly))
