# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
print("总笔数:", len(led))
print("状态分布:", dict(Counter(t.get("status") for t in led)))
print("\n按来源:")
for src, cnt in Counter(t.get("source", "?") for t in led).items():
    print(f"  {src}: {cnt}")
print("\n8-17 起信号状态:")
new = [t for t in led if str(t.get("signal_date", "") or t.get("disclose_date", "")) >= "2026-08-17"]
for t in new:
    print(f"  {t.get('code')} {t.get('name')} sig={t.get('signal_date')} {t.get('status')} exit={t.get('exit_reason','-')}")
