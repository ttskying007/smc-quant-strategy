# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
print("状态:", dict(Counter(t.get("status") for t in led)))
active = [t for t in led if t.get("status") in ("OPEN", "FILLED")]
with_pnl = [t for t in active if t.get("mark_pnl_pct") is not None]
if with_pnl:
    pnls = [t["mark_pnl_pct"] for t in with_pnl]
    print(f"活跃 {len(active)} 笔 | 有浮盈 {len(with_pnl)} | 平均 {sum(pnls)/len(pnls):+.2f}% | 正 {sum(1 for x in pnls if x>0)} 负 {sum(1 for x in pnls if x<0)}")
# tiered TP hit status
tp_hits = sum(1 for t in active if t.get("tp1_hit"))
print(f"TP1 已触发: {tp_hits} 笔")
# recent closed
closed = [t for t in led if t.get("status") == "CLOSED"]
print(f"\nCLOSED {len(closed)} 笔:")
for t in closed[-5:]:
    print(f"  {t.get('code')} {t.get('name')} exit={t.get('exit_reason')} pnl={t.get('pnl_pct')}%")
