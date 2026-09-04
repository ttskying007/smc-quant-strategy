# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
print("状态:", dict(Counter(t.get("status") for t in led)))
active = [t for t in led if t.get("status") != "CLOSED"]
tp1_hit = [t for t in active if t.get("tp1_hit")]
tp2_hit = [t for t in active if t.get("tp2_hit")]
print(f"活跃 {len(active)} | TP1触发 {len(tp1_hit)} | TP2触发 {len(tp2_hit)}")
# exit reasons of closed
closed = [t for t in led if t.get("status") == "CLOSED"]
print(f"CLOSED {len(closed)}: {dict(Counter(t.get('exit_reason') for t in closed))}")
# avg pnl of closed
if closed:
    pnls = [t.get("pnl_pct", 0) for t in closed if t.get("pnl_pct") is not None]
    if pnls:
        print(f"CLOSED 平均: {sum(pnls)/len(pnls):+.2f}% (n={len(pnls)})")
