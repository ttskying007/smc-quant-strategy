# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
active = [t for t in led if t.get("status") != "CLOSED"]
tp1_hit = sum(1 for t in active if t.get("tp1_hit"))
tp2_hit = sum(1 for t in active if t.get("tp2_hit"))
print(f"活跃 {len(active)} | TP1触发 {tp1_hit} | TP2触发 {tp2_hit}")
closed = [t for t in led if t.get("status") == "CLOSED"]
print(f"CLOSED {len(closed)}: {dict(Counter(t.get('exit_reason') for t in closed))}")
# tiered structure sample
print("\n分层 TP/SL 样例:")
for t in active[:3]:
    print(f"  {t.get('code')} {t.get('name')} TP1={t.get('tp1')} TP2={t.get('tp2')} TP3={t.get('tp3')} SL1={t.get('sl1')} SL2={t.get('sl2')} 触发={t.get('tp1_hit','否')}/{t.get('tp2_hit','否')}")
