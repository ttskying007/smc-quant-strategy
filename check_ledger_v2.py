# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
print("状态:", dict(Counter(t.get("status") for t in led)))
# signal dates >= 8-17
new = [t for t in led if str(t.get("signal_date", "") or t.get("disclose_date", "")) >= "2026-08-17"]
print(f"8-17 起新信号 {len(new)} 笔:")
for t in new:
    print(f"  {t.get('code')} {t.get('name')} sig={t.get('signal_date')} status={t.get('status')} pnl={t.get('pnl_pct','')}%")