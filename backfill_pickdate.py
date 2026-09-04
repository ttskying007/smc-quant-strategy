# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = r"E:\test\smc_project\research\paper_ledger.json"
led = json.load(open(p, encoding="utf-8"))
n = 0
for t in led:
    if not t.get("pick_date"):
        t["pick_date"] = t.get("created_at") or t.get("signal_date") or t.get("disclose_date") or "-"
        n += 1
json.dump(led, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"backfill pick_date: {n} 笔")
# summary: pick_date distribution
from collections import Counter
print("选股日期分布:", dict(Counter(t.get("pick_date") for t in led)))
