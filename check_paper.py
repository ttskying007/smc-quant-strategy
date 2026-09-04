# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
from collections import Counter
print("持仓数:", len(led), "状态:", dict(Counter(t.get("status") for t in led)))
closed = [t for t in led if t.get("status") == "CLOSED"]
if closed:
    pnls = [t["pnl_pct"] for t in closed]
    w = sum(1 for p in pnls if p > 0)
    print(f"已平仓 {len(closed)}: WR={100*w/len(closed):.0f}% avg={sum(pnls)/len(pnls):+.2f}%")
    for t in closed[:8]:
        print(" ", t.get("code"), t.get("entry_date"), "->", t.get("exit_date"), f"{t.get('pnl_pct'):+.2f}%")
marks = [t.get("mark_pnl_pct") for t in led if t.get("status") == "OPEN" and t.get("mark_pnl_pct") is not None]
if marks:
    print(f"OPEN {len(marks)}: avg浮盈={sum(marks)/len(marks):+.2f}%")
