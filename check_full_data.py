# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
s = json.load(open(r"E:\test\smc_project\research\current_scanner_result.json", encoding="utf-8"))
print(f"scanner: fresh={s.get('fresh_count')} stale={s.get('stale_count')} coverage={s.get('coverage_pct')}%")
ev = s.get("event_candidates") or []
cont = s.get("continuation_candidates") or []
smc = s.get("smc_candidates") or []
print(f"事件候选: {len(ev)} | 延续候选: {len(cont)} | SMC候选: {len(smc)}")
print(f"latest: {s.get('latest_date')}")
# new picks in ledger
led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
new = [t for t in led if str(t.get("signal_date", "") or t.get("disclose_date", "")) >= "2026-08-19"]
print(f"\n8-19 起新信号: {len(new)} 笔")
for t in new:
    print(f"  {t.get('code')} {t.get('name')} sig={t.get('signal_date')} status={t.get('status')} stage={t.get('stage','')} rank={t.get('rank_score','')}")
