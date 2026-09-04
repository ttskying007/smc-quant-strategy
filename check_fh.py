# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
fh = [t for t in led if t.get("code") == "000636"]
print("风华高科:", json.dumps({k: fh[0].get(k) for k in ("code","name","signal_combo","signal_date","entry_price","tp_price","sl_price","status")}, ensure_ascii=False) if fh else "无")
from collections import Counter
print("状态:", dict(Counter(t.get("status") for t in led)))
pend = [t for t in led if t.get("status") == "PENDING_ORDER"]
print("PENDING:", len(pend), [(t["code"], t.get("signal_combo")) for t in pend[:3]])
