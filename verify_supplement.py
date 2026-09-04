# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
print("状态:", dict(Counter(t.get("status") for t in led)))
new = [t for t in led if str(t.get("signal_date", "") or t.get("disclose_date", "")) >= "2026-08-15"]
print(f"8-15 起新信号: {len(new)} 笔")
for t in new:
    print(f"  {t.get('code')} {t.get('name')} sig={t.get('signal_date')} {t.get('status')} combo={t.get('signal_combo')}")
