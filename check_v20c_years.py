# -*- coding: utf-8 -*-
import csv, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)
years = Counter(str(t["entry_date"])[:4] for t in trades)
print("v20c 年份分布:", dict(sorted(years.items())))
# check cont only
cont = [t for t in trades if t.get("src") == "CONT"]
print("CONT 年份:", dict(Counter(str(t["entry_date"])[:4] for t in cont)))
ev = [t for t in trades if t.get("src") == "EVENT"]
print("EVENT 年份:", dict(Counter(str(t["entry_date"])[:4] for t in ev)))
