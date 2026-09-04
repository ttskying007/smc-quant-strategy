# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
from collections import Counter
print("持仓:", len(led), dict(Counter(t.get("status") for t in led)))
marks = [t.get("mark_pnl_pct") for t in led if t.get("mark_pnl_pct") is not None]
if marks:
    w = sum(1 for m in marks if m > 0)
    print(f"OPEN 持仓 {len(marks)}: WR(浮盈)={100*w/len(marks):.0f}% avg={sum(marks)/len(marks):+.2f}%")
    marks.sort()
    print(f"  分布: min={marks[0]:+.1f}% med={marks[len(marks)//2]:+.1f}% max={marks[-1]:+.1f}%")
# entry dates distribution
from collections import Counter as C2
print("入场日分布:", dict(C2(str(t.get('entry_date',''))[:8] for t in led)))
