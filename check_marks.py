# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
active = [t for t in led if t.get("status") in ("OPEN", "FILLED", "PENDING_ORDER")]
pnls = [t.get("mark_pnl_pct") for t in active if t.get("mark_pnl_pct") is not None]
if pnls:
    print(f"活跃 {len(active)} 笔 | 有浮盈数据 {len(pnls)} 笔 | 平均浮盈 {sum(pnls)/len(pnls):+.2f}% | 正 {sum(1 for x in pnls if x>0)} 负 {sum(1 for x in pnls if x<0)}")
# 8-17+ new signals mark pnl
new = [t for t in active if str(t.get("signal_date", "") or t.get("disclose_date", "")) >= "2026-08-17"]
print(f"\n8-17 起新信号活跃 {len(new)} 笔:")
for t in new:
    mp = t.get("mark_pnl_pct")
    print(f"  {t.get('code')} {t.get('name')} sig={t.get('signal_date')} status={t.get('status')} 浮盈={mp if mp is None else round(mp,2)}%")
