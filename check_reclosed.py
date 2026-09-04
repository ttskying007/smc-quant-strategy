# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
closed = [t for t in led if t.get("status") == "CLOSED"]
print("CLOSED:", len(closed))
print("exit_reason 分布:", dict(Counter(t.get("exit_reason") for t in closed)))
print("pnl 分布:", dict(Counter("<-90%" if (t.get('pnl_pct') or 0) < -90 else ("-50~-90" if (t.get('pnl_pct') or 0) < -50 else ">-50%") for t in closed)))
# sample
for t in closed[:3]:
    print(f"  {t.get('code')} {t.get('name')} exit={t.get('exit_reason')} pnl={t.get('pnl_pct')} filled={t.get('filled_at')} note={t.get('note','-')}")
