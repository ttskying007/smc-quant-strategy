# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
print("状态分布:", dict(Counter(t.get("status") for t in led)))
filled = [t for t in led if t.get("status") == "FILLED"]
print(f"\nFILLED {len(filled)} 笔（样例）:")
for t in filled[:5]:
    print(f"  {t['code']} {t['name']} sig={t.get('signal_combo')} signal={t.get('signal_date')} entry={t.get('entry_price')} tp={t.get('tp_price')} sl={t.get('sl_price')} filled@{t.get('filled_price')}")
pending = [t for t in led if t.get("status") == "PENDING_ORDER"]
print(f"\nPENDING {len(pending)} 笔（未成交，实时价高于挂单价）:")
for t in pending[:5]:
    print(f"  {t['code']} {t['name']} entry={t.get('entry_price')} tp={t.get('tp_price')} sl={t.get('sl_price')}")
# old OPEN (74 legacy)
old = [t for t in led if t.get("status") == "OPEN"]
print(f"\n旧 OPEN（遗留 74，无 TP/SL）: {len(old)}")
