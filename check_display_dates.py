# -*- coding: utf-8 -*-
import json, io, sys
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 1. ledger signal dates distribution
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
open_pos = [t for t in led if t.get("status") != "CLOSED"]
sig_dates = sorted(set(str(t.get("signal_date", "") or t.get("disclose_date", "")) for t in open_pos), reverse=True)
print(f"OPEN 持仓 {len(open_pos)} 笔, 信号日期: {sig_dates[:10]}")

# 2. recent event candidates in scanner result
s = json.load(open(r"E:\test\smc_project\research\current_scanner_result.json", encoding="utf-8"))
ev = s.get("event_candidates") or []
ev_dates = sorted(set(str(e.get("date", "")) for e in ev), reverse=True)
print(f"scanner 事件候选: {len(ev)} 笔, 披露日期: {ev_dates[:5]}")
if ev:
    print("  样例:", [(e.get('date'), e.get('code'), str(e.get('title',''))[:20]) for e in ev[:5]])

# 3. combo dashboard event candidates
try:
    cb = json.load(open(r"E:\test\smc_project\research\combo_dashboard.json", encoding="utf-8"))
    sc = cb.get("current_scanner") or {}
    cev = sc.get("event_candidates") or []
    ced = sorted(set(str(e.get("date", "")) for e in cev), reverse=True)
    print(f"\ncombo_dashboard 事件候选: {len(cev)} 笔, 披露日期: {ced[:5]}")
except Exception as e:
    print("combo_dashboard:", e)
