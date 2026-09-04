# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
from collections import Counter
print("状态:", dict(Counter(t.get("status") for t in led)))
closed = [t for t in led if t.get("status") == "CLOSED"]
print(f"\nCLOSED {len(closed)} 笔:")
for t in closed:
    print(f"  {t['code']} {t['name']} reason={t.get('exit_reason')} pnl={t.get('pnl_pct'):+.2f}% tp={t.get('tp_price')} sl={t.get('sl_price')}")
# TP/SL stats for active
active = [t for t in led if t.get("status") in ("FILLED", "OPEN")]
marks = [t.get("mark_pnl_pct") for t in active if t.get("mark_pnl_pct") is not None]
if marks:
    w = sum(1 for m in marks if m > 0)
    print(f"\n活跃 {len(active)}: 平均浮盈 {sum(marks)/len(marks):+.2f}% WR {100*w/len(marks):.0f}%")
