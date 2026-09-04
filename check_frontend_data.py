# -*- coding: utf-8 -*-
import json, io, os, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
# selection report
try:
    s = json.load(open(r"E:\test\smc_project\research\selection_report.json", encoding="utf-8"))
    print("选股报告:", json.dumps(s, ensure_ascii=False)[:300])
except Exception as e:
    print("selection_report:", e)
# ledger status detail
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
from collections import Counter
print("\nledger 状态:", dict(Counter(t.get("status") for t in led)))
# filled/pending recent
recent = [t for t in led if str(t.get("signal_date", "") or t.get("disclose_date", "")) >= "2026-08-19"]
print(f"\n8-19 起信号: {len(recent)} 笔")
for t in recent:
    print(f"  {t.get('code')} {t.get('name')} sig={t.get('signal_date')} {t.get('status')} filled={t.get('filled_at','-')} mp={t.get('mark_pnl_pct')}")
