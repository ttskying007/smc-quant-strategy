# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
open_old = [t for t in led if t.get("status") == "OPEN"]
print(f"OPEN {len(open_old)} 笔")
# check fields needed for auto-exit
has_hold = sum(1 for t in open_old if t.get("hold"))
has_tiered = sum(1 for t in open_old if t.get("tp1"))
print(f"有 hold 字段: {has_hold} | 有分层TP1: {has_tiered}")
# sample
for t in open_old[:3]:
    print(f"  {t.get('code')} {t.get('name')} sig={t.get('signal_date')} hold={t.get('hold','无')} source={t.get('source')} filled_at={t.get('filled_at','无')}")
